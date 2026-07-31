#pragma once

#include "AP_Baro_Backend.h"
#include <AP_HAL/AP_HAL.h>

class AP_Baro_Analog : public AP_Baro_Backend {
public:
  void update() override;

  static AP_Baro_Backend *probe(AP_Baro &baro, uint8_t pin);

private:
  AP_Baro_Analog(AP_Baro &baro, uint8_t pin);

  bool _init();

  AP_HAL::AnalogSource *_analog_source;

  uint8_t _instance;
  uint8_t _pin;
};
