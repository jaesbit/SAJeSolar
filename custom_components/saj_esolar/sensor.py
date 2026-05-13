"""SAJ eSolar sensor platform — powered by pysaj-elekeeper."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import voluptuous as vol
from elekeeper import PlantOverview, SajApiError, SajAuthError, SajClient

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)

CONF_PLANT_ID: str = "plant_id"
CONF_PLANT_UID: str = "plant_uid"
CONF_BASE_URL: str = "base_url"

SENSOR_PREFIX = "esolar "
DEFAULT_BASE_URL = "https://eop.saj-electric.com"
SCAN_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class SajSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a value accessor for PlantOverview."""

    value_fn: Callable[[PlantOverview], Any] | None = None


# Keys and names are kept identical to the legacy integration to avoid breaking
# existing entity_ids, automations, and dashboards.
SENSOR_TYPES: tuple[SajSensorDescription, ...] = (
    # ── Live power ─────────────────────────────────────────────────────
    SajSensorDescription(
        key="nowPower",
        name="nowPower",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.pv_power_w,
    ),
    SajSensorDescription(
        key="pvPower",
        name="pvPower",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.pv_power_w,
    ),
    SajSensorDescription(
        key="solarPower",
        name="solarPower",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.pv_power_w,
    ),
    SajSensorDescription(
        key="homeLoadPower",
        name="homeLoadPower",
        icon="mdi:home-lightning-bolt-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.load_power_w,
    ),
    SajSensorDescription(
        key="outPower",
        name="outPower",
        icon="mdi:home-lightning-bolt-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.load_power_w,
    ),
    SajSensorDescription(
        key="totalLoadPower",
        name="totalLoadPower",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.load_power_w,
    ),
    SajSensorDescription(
        key="gridPower",
        name="gridPower",
        icon="mdi:transmission-tower",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.grid_power_w,
    ),
    SajSensorDescription(
        key="totalGridPower",
        name="totalGridPower",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.grid_power_w,
    ),
    SajSensorDescription(
        key="gridLoadPower",
        name="gridLoadPower",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.grid_power_w,
    ),
    SajSensorDescription(
        key="exportPower",
        name="exportPower",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: (
            abs(o.grid_power_w) if o.grid_power_w is not None and o.grid_power_w < 0 else 0
        ),
    ),
    SajSensorDescription(
        key="solarLoadPower",
        name="solarLoadPower",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.pv_power_w,
    ),
    SajSensorDescription(
        key="totalPvgenPower",
        name="totalPvgenPower",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.pv_power_w,
    ),
    # ── Battery live ────────────────────────────────────────────────────
    SajSensorDescription(
        key="batteryPower",
        name="batteryPower",
        icon="mdi:battery-charging",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_power_w,
    ),
    SajSensorDescription(
        key="batteryDirection",
        name="batteryDirection",
        icon="mdi:battery-charging",
        value_fn=lambda o: o.battery_direction,
    ),
    SajSensorDescription(
        key="gridDirection",
        name="gridDirection",
        icon="mdi:transmission-tower",
        value_fn=lambda o: o.grid_direction,
    ),
    SajSensorDescription(
        key="pvDirection",
        name="pvDirection",
        icon="mdi:solar-power",
        value_fn=lambda o: (
            1 if o.pv_power_w is not None and o.pv_power_w > 0 else 0
        ),
    ),
    SajSensorDescription(
        key="outPutDirection",
        name="outPutDirection",
        icon="mdi:home-lightning-bolt-outline",
        value_fn=lambda o: (
            1 if o.load_power_w is not None and o.load_power_w > 0 else 0
        ),
    ),
    # ── Battery state ───────────────────────────────────────────────────
    SajSensorDescription(
        key="batEnergyPercent",
        name="batEnergyPercent",
        icon="mdi:battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_soc_percent,
    ),
    SajSensorDescription(
        key="batCurr",
        name="batCurr",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_current_a,
    ),
    SajSensorDescription(
        key="batCapcity",
        name="batCapcity",
        icon="mdi:battery-heart",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_soh_percent,
    ),
    SajSensorDescription(
        key="batVoltage",
        name="batVoltage",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_voltage_v,
    ),
    SajSensorDescription(
        key="batTemperature",
        name="batTemperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.battery_temperature,
    ),
    # ── Today energy ────────────────────────────────────────────────────
    SajSensorDescription(
        key="todayElectricity",
        name="todayElectricity",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_pv_energy_kwh,
    ),
    SajSensorDescription(
        key="pvElec",
        name="pvElec",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda o: o.today_pv_energy_kwh,
    ),
    SajSensorDescription(
        key="useElec",
        name="useElec",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_load_energy_kwh,
    ),
    SajSensorDescription(
        key="buyElec",
        name="buyElec",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_grid_import_kwh,
    ),
    SajSensorDescription(
        key="sellElec",
        name="sellElec",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_grid_export_kwh,
    ),
    SajSensorDescription(
        key="chargeElec",
        name="chargeElec",
        icon="mdi:battery-charging",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_battery_charge_kwh,
    ),
    SajSensorDescription(
        key="dischargeElec",
        name="dischargeElec",
        icon="mdi:battery-minus",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.today_battery_discharge_kwh,
    ),
    # ── Total / lifetime energy ─────────────────────────────────────────
    SajSensorDescription(
        key="totalElectricity",
        name="totalElectricity",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_pv_energy_kwh,
    ),
    SajSensorDescription(
        key="totalPvEnergy",
        name="totalPvEnergy",
        icon="mdi:solar-panel-large",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_pv_energy_kwh,
    ),
    SajSensorDescription(
        key="totalLoadEnergy",
        name="totalLoadEnergy",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_load_energy_kwh,
    ),
    SajSensorDescription(
        key="totalConsumpElec",
        name="totalConsumpElec",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda o: o.total_load_energy_kwh,
    ),
    SajSensorDescription(
        key="totalBuyElec",
        name="totalBuyElec",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_grid_import_kwh,
    ),
    SajSensorDescription(
        key="totalBuyEnergy",
        name="totalBuyEnergy",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_grid_import_kwh,
    ),
    SajSensorDescription(
        key="totalSellElec",
        name="totalSellElec",
        icon="mdi:solar-panel",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_grid_export_kwh,
    ),
    SajSensorDescription(
        key="totalSellEnergy",
        name="totalSellEnergy",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.total_grid_export_kwh,
    ),
    # ── Plant metadata ──────────────────────────────────────────────────
    SajSensorDescription(
        key="runningState",
        name="runningState",
        icon="mdi:solar-panel",
        value_fn=lambda o: o.mode,
    ),
    SajSensorDescription(
        key="lastUploadTime",
        name="lastUploadTime",
        icon="mdi:timer-sand",
        value_fn=lambda o: o.updated_at,
    ),
    SajSensorDescription(
        key="plantname",
        name="plantname",
        icon="mdi:api",
        value_fn=lambda o: o.name,
    ),
    SajSensorDescription(
        key="plantuid",
        name="plantuid",
        icon="mdi:api",
        value_fn=lambda o: o.uid,
    ),
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_PLANT_UID): cv.string,
        vol.Optional(CONF_PLANT_ID, default=0): cv.positive_int,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> bool:
    """Set up the SAJ eSolar sensor platform."""
    username: str = config[CONF_USERNAME]
    password: str = config[CONF_PASSWORD]
    plant_uid: str | None = config.get(CONF_PLANT_UID)
    base_url: str = config.get(CONF_BASE_URL, DEFAULT_BASE_URL)

    http_client = httpx.AsyncClient(timeout=45.0)
    saj_client = SajClient(base_url=base_url, client=http_client)

    coordinator = SajDataCoordinator(
        hass,
        saj_client=saj_client,
        username=username,
        password=password,
        plant_uid=plant_uid,
    )

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        SajSensor(coordinator, description)
        for description in SENSOR_TYPES
    )
    return True


class SajDataCoordinator(DataUpdateCoordinator[PlantOverview]):
    """Fetch data from SAJ Elekeeper via pysaj-elekeeper."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        saj_client: SajClient,
        username: str,
        password: str,
        plant_uid: str | None,
    ) -> None:
        self._client = saj_client
        self._username = username
        self._password = password
        self._plant_uid = plant_uid

        super().__init__(
            hass,
            _LOGGER,
            name="SAJ Elekeeper",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> PlantOverview:
        try:
            await self._client.login(self._username, self._password)
            overview = await self._client.get_plant_overview(self._plant_uid)
        except SajAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except SajApiError as err:
            raise UpdateFailed(f"SAJ API error: {err}") from err
        except httpx.HTTPError as err:
            raise UpdateFailed(f"Network error: {err}") from err
        return overview


class SajSensor(CoordinatorEntity[SajDataCoordinator], SensorEntity):
    """A single SAJ eSolar sensor backed by pysaj-elekeeper."""

    entity_description: SajSensorDescription

    def __init__(
        self,
        coordinator: SajDataCoordinator,
        description: SajSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        # Keep legacy name format so entity_ids stay identical (sensor.esolar_nowpower, etc.)
        self._attr_name = f"{SENSOR_PREFIX}{description.name}"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None or self.entity_description.value_fn is None:
            return None
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except Exception:  # noqa: BLE001
            return None
