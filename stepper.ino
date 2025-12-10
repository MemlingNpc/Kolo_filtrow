#include <AccelStepper.h>
#include <Wire.h>
#include "AS5600.h"
#define MOTOR_INTERFACE_TYPE 1
#define DIR_PIN 2
#define STEP_PIN 4
#define CTRLA_PIN 18
#define CTRLB_PIN 19
const int STEPS_PER_REVOLUTION = 200;
const int FILTER_COUNT = 8;
const long STEPS_PER_FILTER = STEPS_PER_REVOLUTION / FILTER_COUNT;
const int ENCODER_HOME_POSITION = 510;
const int ENCODER_STEPS_PER_FILTER = 512;
const int ENCODER_TOLERANCE = 15;
const int ENCODER_RANGE = 4096;
const int ENCODER_MID_RANGE = ENCODER_RANGE / 2;
const float HOMING_SPEED = 500;
const float CORRECTION_SPEED = 500;
int currentFilterPosition = 1;
String incomingCommand = ""; 

AccelStepper stepper(MOTOR_INTERFACE_TYPE, STEP_PIN, DIR_PIN);
AS5600 as5600; 
void setup() {
  Serial.begin(115200);
  Wire.begin(32, 33);
  as5600.begin(); 
  pinMode(CTRLA_PIN, OUTPUT);
  pinMode(CTRLB_PIN, OUTPUT);
  digitalWrite(CTRLA_PIN, LOW);
  digitalWrite(CTRLB_PIN, LOW);
  stepper.setMaxSpeed(6000);  
  stepper.setAcceleration(4000); 
  runHomingSequence();
}

void runHomingSequence() {
  stepper.setSpeed(HOMING_SPEED);
  while (true) {
    int currentAngle = as5600.readAngle();
    float degrees = currentAngle * (360.0 / 4095.0);
    Serial.print("Surowy kąt (0-4095): ");
    Serial.print(currentAngle);
    Serial.print("\t Kąt (stopnie): ");
    Serial.println(degrees, 2);
    int error = ENCODER_HOME_POSITION - currentAngle;
    if (error > ENCODER_MID_RANGE) {
      error -= ENCODER_RANGE;
    } else if (error < -ENCODER_MID_RANGE) {
      error += ENCODER_RANGE;
    }
    if (abs(error) <= ENCODER_TOLERANCE) {
      break; 
    }
    if (error > 0) {
      stepper.move(1);
    } else {
      stepper.move(-1);
    }
    stepper.runSpeed();
  }
  stepper.setCurrentPosition(0);
  currentFilterPosition = 1;
}
void loop() {
  checkSerialCommands();
}
void checkSerialCommands() {
  if (Serial.available() > 0) {
    incomingCommand = Serial.readStringUntil('\n');
    incomingCommand.trim();
    parseCommand(incomingCommand);
  }
}
void parseCommand(String command) {
  if (command.startsWith("GOTO:")) {
    String filterIdString = command.substring(5);
    int targetFilter = filterIdString.toInt();
    if (targetFilter >= 1 && targetFilter <= FILTER_COUNT) {
      unsigned long startTime = millis();
      moveFilter(targetFilter, startTime);
    } else {
      Serial.println("ERROR: Invalid filter ID (musi być 1-8)");
    }
  } else {
    Serial.println("ERROR: Unknown command");
  }
}
void moveFilter(int targetFilter, unsigned long startTime) {
  if (targetFilter == currentFilterPosition) {
    unsigned long endTime = millis();
    unsigned long duration = endTime - startTime;
    Serial.println("INFO: Czas zmiany: " + String(duration) + " ms (juz na miejscu)");
    Serial.println("OK:" + String(targetFilter));
    return;
  }

  long targetSteps = (long)(targetFilter - 1) * STEPS_PER_FILTER;

  int targetEncoderPosition = ENCODER_HOME_POSITION + (targetFilter - 1) * ENCODER_STEPS_PER_FILTER;

  stepper.moveTo(targetSteps);
  stepper.runToPosition();
  stepper.setSpeed(CORRECTION_SPEED);
  while (true) {

    int currentAngle = as5600.readAngle();
    float degrees = currentAngle * (360.0 / 4095.0);
    Serial.print("Surowy kąt (0-4095): ");
  Serial.print(currentAngle);
  Serial.print("\t Kąt (stopnie): ");
  Serial.println(degrees, 2);

    int error = targetEncoderPosition - currentAngle;

    if (error > ENCODER_MID_RANGE) {
      error -= ENCODER_RANGE;
    } else if (error < -ENCODER_MID_RANGE) {
      error += ENCODER_RANGE;
    }

    if (abs(error) <= ENCODER_TOLERANCE) {
      break; 
    }

    if (error > 0) {
      stepper.move(1);
    } else {
      stepper.move(-1);
    }

    stepper.runSpeed();
  }
  stepper.setCurrentPosition(targetSteps);
  unsigned long endTime = millis();
  unsigned long duration = endTime - startTime;

  Serial.println("INFO: Czas zmiany: " + String(duration) + " ms");

  currentFilterPosition = targetFilter;
  Serial.println("OK:" + String(currentFilterPosition));
}
