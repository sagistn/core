"""Create a connection to a Visonic PowerMax or PowerMaster Alarm System."""

import logging
import asyncio
import requests.exceptions
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from .pconst import PyPanelCommand

from homeassistant.const import (
    ATTR_CODE,
    ATTR_ENTITY_ID,
    SERVICE_RELOAD,
)

from .client import VisonicClient
from .const import (
    DOMAIN,
    DOMAINCLIENT,
    DOMAINDATA,
    VISONIC_UPDATE_LISTENER,
    DOMAINCLIENTTASK,
    ALARM_PANEL_EVENTLOG,
    ALARM_PANEL_RECONNECT,
    ALARM_PANEL_COMMAND,
    ALARM_SENSOR_BYPASS,
    ATTR_BYPASS,
    CONF_PANEL_NUMBER,
    PANEL_ATTRIBUTE_NAME,
    NOTIFICATION_ID,
    NOTIFICATION_TITLE,
)
#from .create_schema import create_schema, set_defaults
from .create_schema import VisonicSchema

_LOGGER = logging.getLogger(__name__)

def configured_hosts(hass):
    """Return a set of the configured hosts."""
    return len(hass.config_entries.async_entries(DOMAIN))

async def combineSettings(entry):
    """Combine the old settings from data and the new from options."""
    # convert python map to dictionary
    conf = {}
    # the entry.data dictionary contains all the old data used on creation and is a complete set
    for k in entry.data:
        conf[k] = entry.data[k]
    # the entry.config dictionary contains the latest/updated values but may not be a complete set
    for k in entry.options:
        conf[k] = entry.options[k]
    return conf


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old schema configuration entry to new."""
    # This function is called when I change VERSION in the ConfigFlow
    # If the config schema ever changes then use this function to convert from old to new config parameters
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new = {**config_entry.data}
        # TODO: modify Config Entry data

        config_entry.data = {**new}
        config_entry.version = 2

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True

CONF_PANEL = PANEL_ATTRIBUTE_NAME  # this must match the field name in services.yaml
CONF_COMMAND = "command"

# the 4 schemas for the HA service calls
ALARM_SCHEMA_EVENTLOG = vol.Schema(
    {
        vol.Optional(CONF_PANEL, default=0): cv.positive_int,
        vol.Optional(ATTR_CODE, default=""): cv.string,
    }
)

ALARM_SCHEMA_COMMAND = vol.Schema(
    {
        vol.Required(CONF_COMMAND) : cv.enum(PyPanelCommand),
        vol.Optional(CONF_PANEL, default=0): cv.positive_int,
        vol.Optional(ATTR_CODE, default=""): cv.string,
    }
)

ALARM_SCHEMA_RECONNECT = vol.Schema(
    {
        vol.Optional(CONF_PANEL, default=0): cv.positive_int,
    }
)

ALARM_SCHEMA_BYPASS = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_BYPASS, default=False): cv.boolean,
        vol.Optional(ATTR_CODE, default=""): cv.string,
        vol.Optional(CONF_PANEL, default=0): cv.positive_int,
    }
)

configured_panel_list = []

async def async_setup(hass: HomeAssistant, base_config: dict):
    """Set up the visonic component."""
    
    def sendHANotification(message: str):
        """Send a HA notification and output message to log file"""
        _LOGGER.info(message)
        hass.components.persistent_notification.create(
            message, title=NOTIFICATION_TITLE, notification_id=NOTIFICATION_ID
        )

    def getClient(call):
        """Lookup the panel number from the service call and find the client for that panel"""
        if isinstance(call.data, dict):
            if CONF_PANEL in call.data:
                # This should always succeed as we set 0 as the default in the Schema
                panel = call.data[CONF_PANEL]
                # Check each connection to get the requested panel
                for entry in hass.config_entries.async_entries(DOMAIN):
                    client = hass.data[DOMAIN][DOMAINCLIENT][entry.entry_id]
                    if client is not None:
                        if panel == client.getPanelID():
                            return client, panel
                return None, panel
        return None, None
    
    async def service_panel_eventlog(call):
        """Handler for event log service"""
        _LOGGER.info("Event log called")
        client, panel = getClient(call)
        if client is not None:
            await client.service_panel_eventlog(call)
        elif panel is not None:
            sendHANotification(f"Event log failed - Panel {panel} not found")
        else:
            sendHANotification(f"Event log failed - Panel not found")
    
    async def service_panel_reconnect(call):
        """Handler for panel reconnect service"""
        _LOGGER.info("Service Panel reconnect called")
        client, panel = getClient(call)
        if client is not None:
            await client.service_panel_reconnect(call)
        elif panel is not None:
            sendHANotification(f"Service Panel reconnect failed - Panel {panel} not found")
        else:
            sendHANotification(f"Service Panel reconnect failed - Panel not found")
    
    async def service_panel_command(call):
        """Handler for panel command service"""
        _LOGGER.info("Service Panel command called")
        client, panel = getClient(call)
        if client is not None:
            await client.service_panel_command(call)
        elif panel is not None:
            sendHANotification(f"Service Panel command failed - Panel {panel} not found")
        else:
            sendHANotification(f"Service Panel command failed - Panel not found")
    
    async def service_sensor_bypass(call):
        """Handler for sensor bypass service"""
        _LOGGER.info("Service Panel sensor bypass called")
        client, panel = getClient(call)
        if client is not None:
            await client.service_sensor_bypass(call)
        elif panel is not None:
            sendHANotification(f"Service Panel sensor bypass failed - Panel {panel} not found")
        else:
            sendHANotification(f"Service Panel sensor bypass failed - Panel not found")
    
    async def handle_reload(service):
        """Handle reload service call."""
        _LOGGER.info("Domain {0} Service {1} reload called: reloading integration".format(DOMAIN, service))

        current_entries = hass.config_entries.async_entries(DOMAIN)

        reload_tasks = [
            hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]

        await asyncio.gather(*reload_tasks)

    _LOGGER.info("Starting Visonic Component")
    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][DOMAINDATA] = {}
    hass.data[DOMAIN][DOMAINCLIENT] = {}
    hass.data[DOMAIN][DOMAINCLIENTTASK] = {}
    hass.data[DOMAIN][VISONIC_UPDATE_LISTENER] = {}
    # Empty out the lists
    hass.data[DOMAIN]["binary_sensor"] = list()
    hass.data[DOMAIN]["select"] = list()
    hass.data[DOMAIN]["switch"] = list()
    hass.data[DOMAIN]["alarm_control_panel"] = list()
    
    # Install the 4 handlers for the HA service calls
    hass.services.async_register(
        DOMAIN,
        ALARM_PANEL_EVENTLOG,
        service_panel_eventlog,
        schema=ALARM_SCHEMA_EVENTLOG,
    )
    hass.services.async_register(
        DOMAIN, 
        ALARM_PANEL_RECONNECT, 
        service_panel_reconnect, 
        schema=ALARM_SCHEMA_RECONNECT,
    )
    hass.services.async_register(
        DOMAIN,
        ALARM_PANEL_COMMAND,
        service_panel_command,
        schema=ALARM_SCHEMA_COMMAND,
    )
    hass.services.async_register(
        DOMAIN,
        ALARM_SENSOR_BYPASS,
        service_sensor_bypass,
        schema=ALARM_SCHEMA_BYPASS,
    )
    hass.helpers.service.async_register_admin_service(
        DOMAIN,
        SERVICE_RELOAD,
        handle_reload,
    )
    return True

# This function is called with the flow data to create a client connection to the alarm panel
# From one of:
#    - the imported configuration.yaml values that have created a control flow
#    - the original control flow if it existed
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up visonic from a config entry."""
    global configured_panel_list

    _LOGGER.debug("[Visonic Setup] ************* create connection here **************")

    # remove all old settings for this component, previous versions of this integration
    hass.data[DOMAIN][entry.entry_id] = {}

    _LOGGER.info("[Visonic Setup] Starting Visonic with entry id={0} configured panels={1}".format(entry.entry_id, configured_hosts(hass)))
    
    # combine and convert python settings map to dictionary
    conf = await combineSettings(entry)

    panel_id = 0

    if CONF_PANEL_NUMBER in conf:
        panel_id = int(conf[CONF_PANEL_NUMBER])
        _LOGGER.debug("[Visonic Setup] Panel Config has panel number {0}".format(panel_id))
    else: 
        _LOGGER.debug("[Visonic Setup] CONF_PANEL_NUMBER not in configuration, defaulting to panel 0 (before uniqueness check)")

    # Check for unique panel ids or HA gets really confused and we end up make a big mess in the config files.
    if panel_id in configured_panel_list:
        _LOGGER.warning("[Visonic Setup] Panel Number {0} is not Unique, you already have a Panel with this Number".format(panel_id))
        return False

    configured_panel_list.append(panel_id)

    # When here, panel_id should be unique in the panels configured so far.

    _LOGGER.debug("[Visonic Setup] Panel Ident {0}".format(panel_id))
    
    # push the merged data back in to HA and update the title
    hass.config_entries.async_update_entry(entry, title=f"Panel {panel_id}", options=conf)

    # create client and connect to the panel
    try:
        # create the client ready to connect to the panel
        client = VisonicClient(hass, panel_id, conf, entry)
        # Save the client ref
        hass.data[DOMAIN][DOMAINDATA][entry.entry_id] = {}
        # connect to the panel        
        clientTask = hass.async_create_task(client.connect())

        _LOGGER.debug("[Visonic Setup] Setting client ID for entry id {0}".format(entry.entry_id))
        # save the client and its task
        hass.data[DOMAIN][DOMAINCLIENT][entry.entry_id] = client
        hass.data[DOMAIN][DOMAINCLIENTTASK][entry.entry_id] = clientTask
        # add update listener
        hass.data[DOMAIN][VISONIC_UPDATE_LISTENER][entry.entry_id] = entry.add_update_listener(async_options_updated)
        # return true to indicate success
        return True
    except requests.exceptions.ConnectionError as error:
        _LOGGER.error("Visonic Panel could not be reached: [%s]", error)
        raise ConfigEntryNotReady
    return False


# This function is called to terminate a client connection to the alarm panel
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload visonic entry."""
    _LOGGER.debug("************* terminate connection here **************")

    eid = entry.entry_id

    client = hass.data[DOMAIN][DOMAINCLIENT][eid]
    clientTask = hass.data[DOMAIN][DOMAINCLIENTTASK][eid]
    updateListener = hass.data[DOMAIN][VISONIC_UPDATE_LISTENER][eid]

    panelid = client.getPanelID()

    # stop all activity in the client
    await client.service_panel_stop()

    #if updateListener is not None:
    #    updateListener()

    if clientTask is not None:
        clientTask.cancel()

    del hass.data[DOMAIN][DOMAINDATA][eid]
    del hass.data[DOMAIN][DOMAINCLIENT][eid]
    del hass.data[DOMAIN][DOMAINCLIENTTASK][eid]
    del hass.data[DOMAIN][VISONIC_UPDATE_LISTENER][eid]
    
    if panelid in configured_panel_list:
        configured_panel_list.remove(panelid)
    else:
        _LOGGER.debug("************* panel ident {0} not in the panel list **************".format(panelid))

    _LOGGER.debug("************* terminate connection success **************")
    return True


# This function is called when there have been changes made to the parameters in the control flow
async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry):
    """Edit visonic entry."""

    _LOGGER.debug("************* update connection data **************")

    # get the visonic client
    client = hass.data[DOMAIN][DOMAINCLIENT][entry.entry_id]

    # combine and convert python settings map to dictionary
    conf = await combineSettings(entry)

    # update the client parameter set
    client.updateConfig(conf)

    return True
