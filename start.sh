#!/bin/bash
docker run --rm -it --privileged -v /dev:/dev --network=host -v $(pwd):/workspace -w /workspace ardupilot/ardupilot-dev-chibios:sha-f7612cba bash
