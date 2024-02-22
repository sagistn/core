"""Config flow for the connection to a Visonic PowerMax or PowerMaster Alarm System."""

import logging

from .const import (
    CONF_DEVICE_BAUD,
    CONF_DEVICE_TYPE,
    CONF_EXCLUDE_SENSOR,
    CONF_EXCLUDE_X10,
    CONF_SIREN_SOUNDING,
    CONF_PANEL_NUMBER,
)

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PATH, CONF_PORT
from homeassistant.core import callback

from .const import DOMAIN, DOMAINCLIENT, CONF_ALARM_NOTIFICATIONS, CONF_OVERRIDE_CODE
from .create_schema import VisonicSchema

_LOGGER = logging.getLogger(__name__)

# Common class handlers for the creation and editing the control flows
#
#  Creation sequence (using VisonicConfigFlow)
#     - Connection type ("device") so user picks ethernet or usb from a drop down list
#     - User then enters either ethernet or usb parameters
#     - Parameters1
#     - Parameters2
#     - parameters3
#     - parameters4
#
#  Modify/Edit sequence (using VisonicOptionsFlowHandler)
#     - Parameters2
#     - parameters3
#     - parameters4
#     If we achieve Standard Plus or Powerlink with the panel then self.powermaster will be set to False or True, depending on the panel type
#     - if self.powermaster
#     -     parameters5

class MyHandlers(data_entry_flow.FlowHandler):
    """My generic handler for config flow ConfigFlow and OptionsFlow."""

    def __init__(self, config_entry = None):
        """Initialize the config flow."""
        # Do not call the parents init function
        # _LOGGER.debug("MyHandlers init")
        self.myschema = VisonicSchema()
        self.powermaster = False
        self.config = {}
        if config_entry is not None:
            # convert python map to dictionary and set defaults for the options flow handler
            c = self.combineSettings(config_entry)
            self.myschema.set_default_options(options = c)

    def combineSettings(self, entry):
        """Combine the old settings from data and the new from options."""
        conf = {}
        # the entry.data dictionary contains all the old data used on creation and is a complete set
        for k in entry.data:
            conf[k] = entry.data[k]
        # the entry.config dictionary contains the latest/updated values but may not be a complete set
        #     overwrite data with options i.e. overwrite the original settings on creation with the edited settings to get the latest
        for k in entry.options:
            conf[k] = entry.options[k]
        return conf
        
    def toList(self, lst, cfg):
        """Convert to a list."""
        if cfg in lst:
            if isinstance(lst[cfg], str):
                tmplist = lst[cfg].split(",") if lst[cfg] != "" else []
                self.config[cfg] = [item.strip().lower() for item in tmplist]
            else:
                self.config[cfg] = lst[cfg]

    async def _show_form(
        self, step: str = "device", placeholders=None, errors=None
    ):
        """Show the form to the user."""
        # _LOGGER.debug("show_form %s %s %s", step, placeholders, errors)

        ds = None

        if step == "device":
            ds = self.myschema.create_schema_device()
        elif step == "ethernet":
            ds = self.myschema.create_schema_ethernet()
        elif step == "usb":
            ds = self.myschema.create_schema_usb()
        elif step == "parameters1":
            ds = self.myschema.create_schema_parameters1()
        elif step == "parameters2":
            ds = self.myschema.create_schema_parameters2()
        elif step == "parameters3":
            ds = self.myschema.create_schema_parameters3()
        elif step == "parameters4":
            ds = self.myschema.create_schema_parameters4()
        elif step == "parameters5":
            ds = self.myschema.create_schema_parameters5()
        else:
            return self.async_abort(reason="device_error")

        if ds is None:
            # The only way this could happen is one of the create functions have returned None
            _LOGGER.debug("show_form ds is None, step is %s", step)
            return self.async_abort(reason="device_error")

        # _LOGGER.debug("show_form ds = %s", (ds)
        return self.async_show_form(
            step_id=step,
            data_schema=ds,
            errors=errors if errors else {},
            description_placeholders=placeholders if placeholders else {},
        )

    async def async_step_parameters1(self, user_input=None):
        """Config flow step 1."""
        if user_input is not None:
            self.config.update(user_input)
        return await self._show_form(step="parameters2")

    async def async_step_parameters2(self, user_input=None):
        """Config flow step 2."""
        if user_input is not None:
            self.config.update(user_input)
        # _LOGGER.debug(f"async_step_parameters2 {user_input}")
        return await self._show_form(step="parameters3")

    async def async_step_parameters3(self, user_input=None):
        """Config flow step 2."""
        if user_input is not None:
            self.config.update(user_input)
        # _LOGGER.debug(f"async_step_parameters3 {user_input}")
        return await self._show_form(step="parameters4")

    async def async_step_parameters4(self, user_input=None):
        """Config flow step 3."""
        if user_input is not None:
            self.config.update(user_input)

        # _LOGGER.debug("async_step_parameters4 %s", self.config)

        if self.powermaster:
            _LOGGER.debug("Detected a powermaster so asking about B0 parameters")
            return await self._show_form(step="parameters5")

        _LOGGER.debug("Detected a powermax so not asking about B0 parameters")
        return await self.processcomplete()

    async def async_step_parameters5(self, user_input=None):
        """Config flow step 4."""
        # add parameters to config
        self.config.update(user_input)
        return await self.processcomplete()

    async def validate_input(self, data: dict):
        """Validate the input."""
        # Validation to be implemented
        #tmpOCode = data.get(CONF_OVERRIDE_CODE, "")
        #_LOGGER.debug(f'validate_input type={type(tmpOCode)}  value={tmpOCode}')

        # Convert the override code from a float to a string, if set to 0 then empty the string
        tmp : str = str(int(data[CONF_OVERRIDE_CODE]))
        if len(tmp) == 0 or len(tmp) > 4 or (len(tmp) == 1 and tmp == "0"):
            tmp = ""
        elif len(tmp) == 1:
            tmp = "000" + tmp
        elif len(tmp) == 2:
            tmp = "00" + tmp
        elif len(tmp) == 3:
            tmp = "0" + tmp
        
        data[CONF_OVERRIDE_CODE] = tmp        
        
        #tmpOCode = data.get(CONF_OVERRIDE_CODE, "")
        #_LOGGER.debug(f'validate_input type={type(tmpOCode)}  value={tmpOCode}')

        # return a temporary title to use
        return {"title": "Alarm Panel"}

    async def processcomplete(self):
        """Config flow process complete."""
        try:
            info = await self.validate_input(self.config)
            # tmpOCode = self.config.get(CONF_OVERRIDE_CODE, "")
            # _LOGGER.debug(f'processcomplete type={type(tmpOCode)}  value={tmpOCode}')
            if info is not None:
                # convert comma separated string to a list
                if CONF_SIREN_SOUNDING in self.config:
                    self.toList(self.config, CONF_SIREN_SOUNDING)

                if CONF_ALARM_NOTIFICATIONS in self.config:
                    self.toList(self.config, CONF_ALARM_NOTIFICATIONS)

                if CONF_EXCLUDE_SENSOR in self.config:
                    self.toList(self.config, CONF_EXCLUDE_SENSOR)
                    # convert string list to integer list
                    self.config[CONF_EXCLUDE_SENSOR] = [
                        int(i) for i in self.config[CONF_EXCLUDE_SENSOR]
                    ]

                if CONF_EXCLUDE_X10 in self.config:
                    self.toList(self.config, CONF_EXCLUDE_X10)
                    # convert string list to integer list
                    self.config[CONF_EXCLUDE_X10] = [
                        int(i) for i in self.config[CONF_EXCLUDE_X10]
                    ]

                return self.async_create_entry(title=info["title"], data=self.config)
        except Exception as er:  # pylint: disable=broad-except
            _LOGGER.debug("Unexpected exception in config flow  %s", str(er))
            # errors["base"] = "unknown"
        return self.async_abort(reason="device_error")


@config_entries.HANDLERS.register(DOMAIN)
class VisonicConfigFlow(config_entries.ConfigFlow, MyHandlers, domain=DOMAIN):
    """Handle a Visonic flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize options flow."""
        MyHandlers.__init__(self)
        config_entries.ConfigFlow.__init__(self)
        _LOGGER.debug("Visonic ConfigFlow init")

    def dumpMyState(self):
        """Output state to the log file."""
        if self._async_current_entries():
            entries = self._async_current_entries()

            if not entries:
                _LOGGER.debug("No Entries found")

            cur_entry = entries[0]
            is_loaded = cur_entry.state == config_entries.ENTRY_STATE_LOADED

            _LOGGER.debug("Is loaded %s", is_loaded)
        # else:
        #    _LOGGER.debug("Invalid List")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        _LOGGER.debug("Visonic async_get_options_flow")
        return VisonicOptionsFlowHandler(config_entry)

    # ask the user, ethernet or usb
    async def async_step_device(self, user_input=None):
        """Handle the input processing of the config flow."""
        _LOGGER.debug("async_step_device %s", user_input)
        #self.dumpMyState()
        if user_input is not None and CONF_DEVICE_TYPE in user_input and CONF_PANEL_NUMBER in user_input:
            self.config[CONF_PANEL_NUMBER] = max(0, int(user_input[CONF_PANEL_NUMBER]))
            self.config[CONF_DEVICE_TYPE] = user_input[CONF_DEVICE_TYPE].lower()
            if self.config[CONF_DEVICE_TYPE] == "ethernet":
                return await self._show_form(step="ethernet")
            elif self.config[CONF_DEVICE_TYPE] == "usb":
                return await self._show_form(step="usb")
        errors = {}
        errors["base"] = "eth_or_usb"
        return await self._show_form(step="device", errors=errors)

    # ask for the ethernet settings
    async def async_step_ethernet(self, user_input=None):
        """Handle the input processing of the config flow."""
        self.config.update(user_input)
        return await self._show_form(step="parameters1")

    # ask for the usb settings
    async def async_step_usb(self, user_input=None):
        """Handle the input processing of the config flow."""
        self.config.update(user_input)
        return await self._show_form(step="parameters1")

    async def async_step_user(self, user_input=None):
        """Handle a user config flow."""
        # determine if a panel connection has already been made and stop a second connection
        # _LOGGER.debug("Visonic async_step_user")
        #if self._async_current_entries():
            #return self.async_abort(reason="already_configured")
        #self.dumpMyState()

        # is this a raw configuration (not called from importing yaml)
        if not user_input:
            _LOGGER.debug("Visonic in async_step_user - trigger user input")
            return await self._show_form(step="device")

        _LOGGER.debug("Visonic async_step_user - importing a yaml config setup")

        # importing a yaml config setup
        info = await self.validate_input(user_input)
        if info is not None:
            #await self.async_set_unique_id(VISONIC_UNIQUE_NAME)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["title"], data=user_input)
        return self.async_abort(reason="device_error")

    # this is run to import the configuration.yaml parameters
    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        # _LOGGER.debug("Visonic in async_step_import in %s", import_config)
        #self.dumpMyState()

        # convert the yaml file format for the device (ethernet or usb) settings to a flat dictionary structure
        data = {}
        try:
            for k in import_config:
                if k == CONF_DEVICE:
                    # flatten out the structure so the data variable is a simple dictionary
                    device_type = import_config.get(CONF_DEVICE)
                    if device_type[CONF_DEVICE_TYPE] == "ethernet":
                        data[CONF_DEVICE_TYPE] = "ethernet"
                        data[CONF_HOST] = device_type[CONF_HOST]
                        data[CONF_PORT] = device_type[CONF_PORT]
                    elif device_type[CONF_DEVICE_TYPE] == "usb":
                        data[CONF_DEVICE_TYPE] = "usb"
                        data[CONF_PATH] = device_type[CONF_PATH]
                        if CONF_DEVICE_BAUD in device_type:
                            data[CONF_DEVICE_BAUD] = device_type[CONF_DEVICE_BAUD]
                        else:
                            data[CONF_DEVICE_BAUD] = int(9600)
                else:
                    data[k] = import_config.get(k)
        except Exception as er:
            _LOGGER.debug(
                "Importing settings from configuration.yaml but something went wrong or some essential data is missing %s",
                str(er),
            )
            # _LOGGER.debug("     The current data is %s", import_config)
            return self.async_abort(reason="settings_missing")

        return await self.async_step_user(data)


class VisonicOptionsFlowHandler(config_entries.OptionsFlow, MyHandlers):
    """Handle options."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self, config_entry):
        """Initialize options flow."""
        MyHandlers.__init__(self, config_entry)
        config_entries.OptionsFlow.__init__(self)
        self.config = dict(config_entry.options)
        self.entry_id = config_entry.entry_id
        _LOGGER.debug("init %s %s", self.entry_id, self.config)

    # when editing an existing config, start from parameters2 as the previous settings are not editable after the connection has been made
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        # Get the client
        if self.hass is not None:
            client = self.hass.data[DOMAIN][DOMAINCLIENT][self.entry_id]
            if client is not None:
                # From the client, is it a PowerMaster panel (this assumes that the EPROM has been downloaded, or at least the 0x3C data)"
                self.powermaster = client.isPowerMaster()
        _LOGGER.debug("Edit config option settings, powermaster = %s", self.powermaster)
        return await self._show_form(step="parameters2")
