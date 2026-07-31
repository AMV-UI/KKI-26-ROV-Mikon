#include "AP_Baro_Analog.h"
#include <stdio.h>

extern const AP_HAL::HAL &hal;

AP_Baro_Analog::AP_Baro_Analog(AP_Baro &baro, uint8_t pin)
    : AP_Baro_Backend(baro), _analog_source(nullptr), _pin(pin) {}

AP_Baro_Backend *AP_Baro_Analog::probe(AP_Baro &baro, uint8_t pin) {
  AP_Baro_Analog *sensor = NEW_NOTHROW AP_Baro_Analog(baro, pin);
  if (!sensor || !sensor->_init()) {
    delete sensor;
    return nullptr;
  }
  return sensor;
}

bool AP_Baro_Analog::_init() {
  _analog_source = hal.analogin->channel(_pin);

  if (_analog_source == nullptr) {
    return false;
  }

  _instance = _frontend.register_sensor();

  _frontend.set_type(_instance, AP_Baro::BARO_TYPE_WATER);

  return true;
}

void AP_Baro_Analog::update() {
  if (_analog_source == nullptr) {
    return;
  }

  float voltage = _analog_source->voltage_average();

  const float voltage_min = 0.55f;
  const float voltage_max = 2.40f;
  const float pressure_max_pa = 49033.0f;

  float pressure_pa =
      ((voltage - voltage_min) / (voltage_max - voltage_min)) * pressure_max_pa;

  if (pressure_pa < 0.0f) {
    pressure_pa = 0.0f;
  }

  float absolute_pressure_pa = pressure_pa + 101325.0f;

  // static uint8_t debug_counter = 0;
  // if (debug_counter++ >= 50) {
  //   printf("Analog Baro - Pin: %u | Volts: %.3f | Pa: %.1f\n", _pin, voltage,
  //          absolute_pressure_pa);
  //   debug_counter = 0;
  // }

  float temperature_c = 25.0f;

  _copy_to_frontend(_instance, absolute_pressure_pa, temperature_c);
}
