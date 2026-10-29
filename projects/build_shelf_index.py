"""build_shelf_index - write shelf_index.json, the off-the-shelf parts
Atelier offers, from the FreeCAD Parts Library at shelf.REVISION.

    GITHUB_TOKEN=<token, optional> freecadcmd projects/build_shelf_index.py
    SHELF_MODE=authors  freecadcmd ...     # refresh only the authors
    SHELF_MODE=pictures [SHELF_ONLY=a,b] freecadcmd ...  # draw the pictures

CURATED below is the list and everything we SAY about each part: what it
is, its wiring where a datasheet settles it (nothing is said otherwise),
and notes for the agent. Everything else is MEASURED or READ here:
  * path, git blob id and byte size from the repository tree at REVISION;
  * size_mm from the part's own mesh (the STEP downloaded, its blob id
    checked, meshed as user_parts meshes every STEP);
  * authors from the file's git history (the library's licence: "See
    commit details to find the authors of each Part"), oldest first;
  * thumb: the library's own picture of the part's .FCStd, when it has one
    (build_index.py names it md5(quoted path)).png).
The GitHub API allows 60 unauthenticated requests an hour; one per part is
made for its history, so set GITHUB_TOKEN for a full build.
"""
import hashlib
import json
import os
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import shelf  # noqa: E402

E, P, M, W, X = "electronics", "power", "motor", "wheel", "mechanical"


def el(interface=None, voltage_v=None, wiring=None, connectors=None):
    d = {"interface": interface, "voltage_v": voltage_v, "wiring": wiring,
         "connectors": connectors}
    return {k: v for k, v in d.items() if v is not None}


#: key: (group, path, display name, category, electrical, description, agent notes)
CURATED = {
    # ---------------------------------------------------------------- boards
    "arduino_nano": ("boards", "Computing/SingleBoardComputers/Arduino/Nano-Rev3_0.step",
                     "Arduino Nano (Rev3)", E,
                     el("usb", 5, "ATmega328P; 5 V logic", "USB Mini-B; 2 rows of 2.54 mm pins"),
                     "Small microcontroller board (ATmega328P) with a USB Mini-B socket.",
                     "Leave the USB Mini-B socket reachable through a wall opening, and "
                     "room above the pin rows for wires or a socket."),
    "arduino_uno_compatible": ("boards", "Computing/SingleBoardComputers/Arduino/freaduino-uno.step",
                               "Freaduino Uno (Arduino Uno compatible)", E,
                               el("usb", 5, "ATmega328P; 5 V logic"),
                               "Arduino Uno-compatible board (Freaduino), the Uno's size and "
                               "mounting holes.",
                               "Open the USB and DC-jack end of the board to the outside. Mount "
                               "it on standoffs through its holes; leave room above the headers "
                               "for shields or wires."),
    "arduino_mega": ("boards", "Computing/SingleBoardComputers/Arduino/arduino-mega.step",
                     "Arduino Mega 2560", E, el("usb", 5, "ATmega2560; 5 V logic"),
                     "Large Arduino board (ATmega2560) with many pins.",
                     "Open the USB and DC-jack end to the outside; mount it on standoffs "
                     "through its holes; leave room above the headers for wires."),
    "esp32_devkit": ("boards", "Computing/SingleBoardComputers/ESP32/ESP32_DOIT_DevKit_v1/ESP32_DOIT_DevKit_V1.step",
                     "ESP32 DevKit V1 (DOIT)", E,
                     el("usb", None, "ESP32 with Wi-Fi and Bluetooth; 3.3 V logic", "Micro-USB"),
                     "ESP32 Wi-Fi/Bluetooth development board with a Micro-USB socket.",
                     "Keep the antenna end of the module clear of metal and of thick walls "
                     "near it (no metal in front of it); leave the Micro-USB socket reachable."),
    "raspberry_pi_4b": ("boards", "Computing/SingleBoardComputers/Raspberry/Raspberry Pi 4B/Raspberry Pi 4B.step",
                        "Raspberry Pi 4 Model B", E,
                        el("usb", 5, "powered by 5 V over USB-C",
                           "USB-C power, 2 micro-HDMI, 4 USB-A, Ethernet, 3.5 mm jack"),
                        "Single-board computer with USB-C power, two micro-HDMI, four USB-A "
                        "and Ethernet.",
                        "Open the connector edges you need (USB/Ethernet end, USB-C and HDMI "
                        "side) to the outside; it runs warm: vent the case or leave room for a "
                        "heatsink or fan over the processor. Mount on M2.5 standoffs through "
                        "its four holes."),
    "raspberry_pi_pico": ("boards", "Computing/SingleBoardComputers/Raspberry/Raspberry Pi Pico/Pico-R3.step",
                          "Raspberry Pi Pico", E,
                          el("usb", None, "RP2040; 3.3 V logic", "Micro-USB"),
                          "Small RP2040 microcontroller board with a Micro-USB socket.",
                          "Leave the Micro-USB socket reachable and room for pins or wires "
                          "along both long edges."),
    # --------------------------------------------------------------- sensors
    "hc_sr04": ("sensors", "Sensors/Ultrasonic Sensors/HC-SR04.step",
                "HC-SR04 ultrasonic distance sensor", E,
                el("gpio", 5, "trigger and echo pins"),
                "Ultrasonic distance sensor with two round transducers.",
                "Both transducers must look out through the wall: one round hole each, a "
                "little wider than the transducer, with nothing in front of them. Point them "
                "at what is measured."),
    "sharp_gp2y0a41": ("sensors", "Electronics Parts/Optical/SHARP/0A41SK/SHARP-0A41SK.step",
                       "Sharp GP2Y0A41SK0F IR distance sensor (4-30 cm)", E,
                       el("analog", 5, "analog voltage out"),
                       "Infrared distance sensor, 4 to 30 cm, analog output.",
                       "The two lenses (emitter and receiver) must see out: an opening over "
                       "both, or an IR-clear window; never cover them with ordinary plastic."),
    "sharp_gp2y0a02": ("sensors", "Electronics Parts/Optical/SHARP/2Y0A02/SHARP-2Y0A02.step",
                       "Sharp GP2Y0A02YK0F IR distance sensor (20-150 cm)", E,
                       el("analog", 5, "analog voltage out"),
                       "Infrared distance sensor, 20 to 150 cm, analog output.",
                       "The two lenses (emitter and receiver) must see out: an opening over "
                       "both, or an IR-clear window."),
    "maxsonar_mb1010": ("sensors", "Sensors/Ultrasonic Sensors/MaxSonar/MB1010/MaxSonar-MB1010.step",
                        "MaxBotix LV-MaxSonar-EZ1 (MB1010)", E,
                        el("analog", None, "2.5-5.5 V; analog, serial or pulse-width output"),
                        "Ultrasonic range finder with one transducer.",
                        "The transducer must look out through a round hole with nothing in "
                        "front of it."),
    "raspi_camera_wide": ("sensors", "Sensors/Cameras/Wide-170-Angle-Raspi-Camera.step",
                          "Raspberry Pi camera, 170° wide angle", E,
                          el("other", None, None, "CSI ribbon cable"),
                          "Camera board with a 170° wide-angle lens for the Raspberry Pi.",
                          "Its view is very wide: the lens opening must be wide and short "
                          "(countersunk, wider outside) or the case shows in the picture. "
                          "Leave a path for the flat ribbon cable."),
    "photoresistor": ("sensors", "Electronics Parts/Photoresistor/Photoresistor.step",
                      "Photoresistor (LDR)", E, el("analog"),
                      "Light-dependent resistor.",
                      "It reads the light that reaches it: an opening or a clear window over "
                      "its face."),
    "inductive_proximity": ("sensors", "Electronics Parts/Inductors/Inductive_sensor/Inductive-Proximity-Sensor.step",
                            "Inductive proximity sensor (cylindrical)", E, el("gpio"),
                            "Threaded cylindrical sensor that detects metal at its face.",
                            "Mount it by its thread through a wall or bracket hole with its "
                            "two nuts; its face must be free, no metal round the face."),
    "gnss_antenna": ("sensors", "Electronics Parts/Antennas/Antenna-GNSS-STA-901A.step",
                     "GNSS antenna (STA-901A)", E, el("other"),
                     "Satellite-navigation (GPS) antenna.",
                     "It needs a view of the sky: top of the product, under plastic only, "
                     "never under metal."),
    # ---------------------------------------------------------------- motors
    "sg90_servo": ("motors", "Electrical Parts/Servos/SG-90/Servo-sg90.step",
                   "SG90 micro servo", M, el("pwm", 5, "4.8-6 V; PWM signal", "3-wire lead"),
                   "Micro hobby servo, about 180° of travel.",
                   "Hold it by its mounting ears (two screws) in a pocket the body's size; its "
                   "output shaft and horn need room to swing; leave a path for the 3-wire lead."),
    "emax_es08a": ("motors", "Electrical Parts/Servos/Emax-ES08A/Emax-es08A.step",
                   "Emax ES08A micro servo", M, el("pwm", None, "PWM signal", "3-wire lead"),
                   "Micro hobby servo.",
                   "Hold it by its mounting ears in a pocket the body's size; the horn needs "
                   "room to swing."),
    "futaba_s3003": ("motors", "Electrical Parts/Servos/Futaba3003/Futaba3003.stp",
                     "Futaba S3003 standard servo", M, el("pwm", None, "4.8-6 V; PWM signal", "3-wire lead"),
                     "Standard-size hobby servo.",
                     "Hold it by its four mounting ears; the horn needs room to swing."),
    "springrc_sm_s4303r": ("motors", "Electrical Parts/Servos/SpringRC-SM-S4303R/SM-S4303R.step",
                           "SpringRC SM-S4303R continuous-rotation servo", M,
                           el("pwm", None, "PWM signal sets speed and direction", "3-wire lead"),
                           "Standard-size servo that turns continuously (a geared motor "
                           "driven by a servo signal).",
                           "Hold it by its four mounting ears; it can drive a wheel directly "
                           "on its horn."),
    "stepper_28byj48": ("motors", "Electrical Parts/Motors/Stepper/28BYJ-48/28BYJ-48.step",
                        "28BYJ-48 geared stepper motor", M,
                        el("other", 5, "unipolar; needs a driver (ULN2003 board)", "5-wire lead"),
                        "Small 5 V geared stepper motor.",
                        "Mount it by its two ears; the shaft is off-centre. Leave a path for "
                        "the 5-wire lead to its driver board."),
    "nema17_stepper_fc": ("motors", "Electrical Parts/Motors/Stepper/NEMA/NEMA_17_with_connector.step",
                          "NEMA 17 stepper motor (with connector)", M,
                          el("other", None, "bipolar; needs a stepper driver"),
                          "Standard 42 mm stepper motor with its cable connector.",
                          "Mount it by the four screws in its face; leave the connector "
                          "reachable and air round the body (it runs warm)."),
    "tt_gearmotor": ("motors", "Electrical Parts/Motors/DC motor/Yellow_gearmotor/straight/Yellow_gearmotor_straight.step",
                     "TT gear motor (yellow, straight)", M, el("power", None, "about 3-6 V DC"),
                     "The common yellow hobby gear motor, double output shaft.",
                     "Hold it by its two through-holes; a TT wheel fits its shaft. Leave a "
                     "path for its two wires."),
    "tt_gearmotor_l": ("motors", "Electrical Parts/Motors/DC motor/Yellow_gearmotor/L_shape/Yellow_gearmotor_L.step",
                       "TT gear motor (yellow, right angle)", M, el("power", None, "about 3-6 V DC"),
                       "The common yellow hobby gear motor, motor at right angles to the shaft.",
                       "Hold it by its through-holes; a TT wheel fits its shaft."),
    "pololu_micro_298": ("motors", "Electrical Parts/Motors/DC motor/Pololu-Micro/Pololu-298_1-6V.step",
                         "Pololu micro metal gearmotor, 298:1, 6 V", M, el("power", 6),
                         "Tiny metal gearmotor (N20 size), 298:1.",
                         "Clamp the gearbox in a bracket or a pocket with a strap; the motor "
                         "end needs its two terminals reachable."),
    "cqrobot_37d": ("motors", "Electrical Parts/Motors/cqrobot_37d/CQRobot_37D_90to1_64CPR.step",
                    "CQRobot 37D gearmotor, 90:1, with encoder", M,
                    el("power", None, "64 CPR encoder on the motor"),
                    "37 mm metal gearmotor with an encoder.",
                    "Mount it by the screws in its gearbox face; leave room behind the "
                    "encoder for its cable."),
    "faulhaber_2342": ("motors", "Electrical Parts/Motors/DC motor/FAULHABER 2342L-012CPR/FAULHABER_2342L-012CPR.step",
                       "Faulhaber 2342L012CR DC motor", M, el("power", 12),
                       "Precision 23 mm DC motor, 12 V.",
                       "Mount it by the screws in its face; keep its shaft aligned with what "
                       "it drives."),
    "dc_motor_encoder": ("motors", "Electrical Parts/Motors/DC motor/Mabuchi-Encoder/DCMotorEncoder.step",
                         "DC motor with encoder (Mabuchi)", M, el("power"),
                         "Small DC motor with an encoder disc on the back.",
                         "Mount it by its face; leave room behind it for the encoder."),
    "mini_vacuum_pump": ("motors", "Electrical Parts/Motors/Vacuum Pump/Mini vacuum pump.step",
                         "Mini vacuum / air pump", M, el("power"),
                         "Small diaphragm air pump.",
                         "Leave its two nozzles reachable for tubing; it vibrates: mount it on "
                         "soft pads, not hard against the case."),
    "fan_40mm": ("motors", "Electrical Parts/fans/fan-40x40mm.step", "Fan, 40 mm", M, el("power"),
                 "40 mm axial cooling fan.",
                 "Air must reach both faces: a grille in the wall over it (not a solid wall) "
                 "and an inlet elsewhere so air flows through. Mount by its corner holes."),
    "fan_50mm": ("motors", "Electrical Parts/fans/fan-50x50mm.step", "Fan, 50 mm", M, el("power"),
                 "50 mm axial cooling fan.",
                 "A grille over it and an inlet elsewhere; mount by its corner holes."),
    "blower_50mm": ("motors", "Electrical Parts/fans/blower-50x50mm.step", "Blower fan, 50 mm", M,
                    el("power"), "50 mm radial (blower) fan: air in at the face, out at the side.",
                    "Leave its face inlet open and duct its side outlet to a vent."),
    "tt_wheel_65mm": ("motors", "Electrical Parts/Motors/DC motor/Yellow_wheel_65mm/Yellow_wheel_65mm.step",
                      "Wheel for TT gear motor, 65 mm", W, None,
                      "65 mm rubber-tyred wheel that fits the TT gear motor.",
                      "Give it clearance all round inside any wheel arch; it sits on the TT "
                      "motor's shaft."),
    # ----------------------------------------------------------------- power
    "battery_aa": ("power", "Electrical Parts/Batteries/battery-AA.step", "AA battery", P,
                   el("power", 1.5), "AA cell.",
                   "Hold it in a holder or a clip; leave a door to change it."),
    "battery_aaa": ("power", "Electrical Parts/Batteries/battery-AAA.step", "AAA battery", P,
                    el("power", 1.5), "AAA cell.",
                    "Hold it in a holder or a clip; leave a door to change it."),
    "battery_holder_4aaa": ("power", "Electrical Parts/Batteries/battery-holder-4-AAA.step",
                            "Battery holder, 4 × AAA", P, el("power"),
                            "Holder for four AAA cells.",
                            "Put it behind a battery door the user can open; leave a path "
                            "for its two wires."),
    "battery_holder_8aaa": ("power", "Electrical Parts/Batteries/battery-holder-8-AAA.step",
                            "Battery holder, 8 × AAA", P, el("power"),
                            "Holder for eight AAA cells.",
                            "Put it behind a battery door the user can open."),
    "lipo_240mah": ("power", "Electrical Parts/Batteries/battery_lipo_3_7v_240mAh.step",
                    "LiPo battery, 3.7 V 240 mAh", P, el("power", 3.7),
                    "Small lithium-polymer pouch cell.",
                    "Give it a pocket with a little room to swell, nothing sharp against it, "
                    "away from hot parts; never clamp it."),
    "lm2596_buck": ("power", "Electrical Parts/DCDC/LM2596S_Buck_Module_43x21/LM2596S_Buck_Module_43x21.step",
                    "LM2596 buck converter module", P,
                    el("power", None, "adjustable step-down regulator (LM2596S)"),
                    "Adjustable step-down voltage regulator board.",
                    "Leave its trim potentiometer reachable (or set it before closing) and "
                    "air over its inductor and chip."),
    "l298n_driver": ("power", "Electrical Parts/Motor Drivers/L298N/L298N.step",
                     "L298N dual motor driver", E,
                     el("gpio", None, "dual H-bridge: two DC motors or one stepper"),
                     "Dual H-bridge motor driver board with a heatsink.",
                     "Its heatsink gets hot: vents over it and no wall touching it. Leave its "
                     "screw terminals reachable."),
    "dhb12_driver": ("power", "Electrical Parts/Motor Drivers/DHB12/DHB12.stp",
                     "DHB12 motor driver", E, el("gpio"),
                     "DC motor driver board.",
                     "Leave its terminals reachable and air over it."),
    "dc_jack_2_1mm": ("power", "Electronics Parts/Connectors/power-connectors/jack_DC_2.1mm_PCB.step",
                      "DC barrel jack, 2.1 mm (PCB)", P, el("power"),
                      "Power socket for a 2.1 mm barrel plug.",
                      "Its mouth must sit at a wall with a round opening and room outside "
                      "for the plug."),
    "fuse_mf_r500": ("power", "Electronics Parts/Fuses/THT/fuse-MF-R500.step",
                     "Resettable fuse, Bourns MF-R500", P, el("power"),
                     "Polymer PTC resettable fuse.", ""),
    "irm60_psu": ("power", "Electrical Parts/Power Supplies/IRM-60 ST series power supply/IRM-60 ST power supply.step",
                  "Mean Well IRM-60 AC-DC module", P,
                  el("power", None, "MAINS input (AC); low-voltage DC output"),
                  "Encapsulated 60 W mains-to-DC power module.",
                  "MAINS VOLTAGE: only for a design whose maker knows mains safety. Fully "
                  "enclosed, no openings a finger or tool can reach live parts through, a "
                  "proper strain-relieved mains inlet, and the low-voltage side kept apart."),
    "switching_psu": ("power", "Electrical Parts/Power Supplies/Switching power supply/Switching power supply.step",
                      "Switching power supply (enclosed)", P,
                      el("power", None, "MAINS input (AC); DC output"),
                      "Enclosed mains-to-DC power supply with screw terminals.",
                      "MAINS VOLTAGE: cover its terminal block, keep its vents open, and use a "
                      "proper mains inlet with strain relief."),
    # -------------------------------------------------------------- controls
    "push_button_22mm_red": ("controls", "Electrical Parts/Push buttons/Red Push-button - 22 mm.step",
                             "Panel push button, 22 mm (red)", E, el("gpio"),
                             "Industrial panel push button for a 22 mm hole.",
                             "It mounts through a 22 mm panel hole (about 22.3 mm) in a wall "
                             "no thicker than its thread allows; its contact block hangs "
                             "behind the wall and needs room."),
    "push_button_22mm_green": ("controls", "Electrical Parts/Push buttons/Green Push-button - 22 mm.step",
                               "Panel push button, 22 mm (green)", E, el("gpio"),
                               "Industrial panel push button for a 22 mm hole.",
                               "It mounts through a 22 mm panel hole; its contact block needs "
                               "room behind the wall."),
    "emergency_stop_22mm": ("controls", "Electrical Parts/Push buttons/Emergency stop mushroom head push-button - 22 mm.step",
                            "Emergency-stop button, 22 mm", E, el("gpio"),
                            "Red mushroom-head emergency-stop button for a 22 mm hole.",
                            "Put it where a hand finds it at once, on top or the front, "
                            "nothing round it to catch; 22 mm panel hole."),
    "cherry_mx_switch": ("controls", "Electronics Parts/Buttons/THT/cherry-mx-basic.step",
                         "Cherry MX key switch", E, el("gpio"),
                         "Mechanical keyboard switch.",
                         "It clips into a 14 mm square plate hole in a 1.5 mm plate; a key "
                         "cap goes on its stem."),
    "tactile_button": ("controls", "Electronics Parts/Buttons/THT/pushbutton-mini.step",
                       "Tactile push button (PCB)", E, el("gpio"),
                       "Small through-hole tactile switch.",
                       "Bring a plunger or a flexible button in the case down onto it; "
                       "leave a little travel."),
    "tactile_button_right_angle": ("controls", "Electronics Parts/Buttons/THT/pushbutton-right-angle.step",
                                   "Tactile push button, right angle (PCB)", E, el("gpio"),
                                   "Side-pressed tactile switch for a board edge.",
                                   "Its plunger faces sideways: put it at a wall with a "
                                   "button or opening in front."),
    "rocker_switch_round": ("controls", "Electronics Parts/Switch/Box/RoundRockerSwitch2Pins.step",
                            "Round rocker switch (2 pins)", P, el("power"),
                            "Snap-in round on/off rocker switch.",
                            "It snaps into a round panel hole the size of its body; leave room "
                            "behind for its two terminals."),
    "slide_switch": ("controls", "Electronics Parts/Switch/THT/slide-sw-spdt.step",
                     "Slide switch, SPDT (PCB)", E, el("gpio"),
                     "Small slide switch.",
                     "Its lever needs a slot in the wall a little longer than its travel."),
    "toggle_switch_1p2t": ("controls", "Electronics Parts/Switch/Mini toggle switch 1P2T/Interuptor conmutador 1P2T PCB.step",
                           "Mini toggle switch, 1P2T", E, el("gpio"),
                           "Small toggle switch.",
                           "Mount it through a panel hole by its threaded bushing and nut."),
    "microswitch_lever": ("controls", "Electronics Parts/Switch/Limit switch/Microswitch_SPDT_Vertical.step",
                          "Microswitch with lever (SPDT)", E, el("gpio"),
                          "Snap-action limit switch with a lever.",
                          "Mount it by its two holes where the moving part presses the lever; "
                          "leave over-travel."),
    "endstop_makerbot": ("controls", "Electrical Parts/Endstop/endstop-v1-2-makerbot.step",
                         "Mechanical endstop board (MakerBot v1.2)", E, el("gpio"),
                         "Microswitch endstop on a small board, as on 3D printers.",
                         "Mount it by its holes where the moving part presses the lever."),
    "rotary_encoder": ("controls", "Electronics Parts/Rotatory encoders/rotatory-encoder.step",
                       "Rotary encoder with push switch", E, el("gpio"),
                       "Rotary encoder knob shaft with a push switch.",
                       "Its threaded bushing mounts through a panel hole with its nut; a knob "
                       "goes on the shaft outside."),
    "potentiometer": ("controls", "Electronics Parts/Potentiometer/Potentiometer.step",
                      "Potentiometer", E, el("analog"),
                      "Rotary potentiometer.",
                      "Its bushing mounts through a panel hole with its nut; a knob goes on "
                      "the shaft outside."),
    # -------------------------------------------------------------- displays
    "led_5mm": ("displays", "Electronics Parts/LEDs/led-5mm.step", "LED, 5 mm", E, el("gpio"),
                "Through-hole 5 mm LED.",
                "Its dome can poke through a 5 mm hole, or sit behind a light pipe or a "
                "thin diffuser."),
    "led_3mm": ("displays", "Electronics Parts/LEDs/led-3mm-short.step", "LED, 3 mm", E, el("gpio"),
                "Through-hole 3 mm LED.", "Through a 3 mm hole, or behind a light pipe."),
    "rgb_led_5mm": ("displays", "Electronics Parts/LEDs/RGB-LED-5mm.step", "RGB LED, 5 mm", E,
                    el("gpio"), "Through-hole 5 mm RGB LED (four legs).",
                    "Behind a diffuser the colours mix; through a hole they show apart."),
    "led_bargraph": ("displays", "Electronics Parts/LEDs/bargraph.step", "LED bar graph", E,
                     el("gpio"), "Ten-segment LED bar graph.",
                     "A window over its face; nothing in front of the segments."),
    "buzzer": ("displays", "Electronics Parts/Buzzers/Buzzer.step", "Buzzer", E, el("gpio"),
               "Small round buzzer.",
               "Sound must get out: a hole or a few small holes over its opening."),
    "seven_segment": ("displays", "Electronics Parts/Displays/Display 7 segmentos/Archivos/Display 7 segmentos.step",
                      "7-segment LED display", E, el("gpio"),
                      "One-digit 7-segment LED display.",
                      "A window or a tinted panel over its face."),
    "lcd_20x4": ("displays", "Electronics Parts/Displays/LCD/lcd-4x20-backlight.step",
                 "LCD, 20 × 4 characters (backlit)", E, el("other"),
                 "Character LCD module, four lines of 20.",
                 "A window the size of its viewing area in the front; mount the board by its "
                 "four corner holes behind the wall."),
    "tft_2_4in": ("displays", "Electronics Parts/Displays/TFT/2-4_tft_spi_240x320.step",
                  "TFT display, 2.4 in, 240 × 320 (SPI)", E, el("spi"),
                  "Colour TFT display on a carrier board.",
                  "A window over the screen area only; mount the board by its holes behind "
                  "the wall."),
    "tft_3_5in_rpi": ("displays", "Electronics Parts/Displays/TFT/3.5_RPi_tft_display_spi_480x320.step",
                      "TFT display, 3.5 in, 480 × 320, for Raspberry Pi (SPI)", E, el("spi"),
                      "Colour TFT display that plugs onto a Raspberry Pi's header.",
                      "A window over the screen; it sits on the Pi's header, so design the two "
                      "together."),
    # ------------------------------------------------------------ connectors
    "usb_b_jack": ("connectors", "Electronics Parts/Connectors/USB-connectors/USB-2_0-type-B-jack-PCB.step",
                   "USB-B socket (PCB)", E, el("usb"), "USB 2.0 type-B socket.",
                   "Its mouth at a wall with an opening a little larger than the plug, and "
                   "room outside for the plug."),
    "usb_a_dual": ("connectors", "Electronics Parts/Connectors/USB-connectors/USB-2_0-type-A-Dual-Stacked-jack-PCB.step",
                   "USB-A socket, dual stacked (PCB)", E, el("usb"), "Two stacked USB 2.0 type-A sockets.",
                   "Its mouths at a wall with an opening round both."),
    "usb_micro_b": ("connectors", "Electronics Parts/Connectors/USB-connectors/smd/USB-micro-B.step",
                    "Micro-USB socket", E, el("usb"), "USB Micro-B socket.",
                    "Its mouth at a wall; the opening must clear the plug's overmould, not "
                    "only its metal."),
    "rj45_jack": ("connectors", "Electronics Parts/Connectors/Ethernet-connectors/rj45-ethernet-PCB-with-leds.step",
                  "RJ45 Ethernet socket with LEDs", E, el("other"), "Ethernet socket with status LEDs.",
                  "Its mouth at a wall with room for the plug's latch to be pressed."),
    "hdmi_jack": ("connectors", "Electronics Parts/Connectors/HDMI-connectors/hdmi-connector.step",
                  "HDMI socket", E, el("other"), "Full-size HDMI socket.",
                  "Its mouth at a wall with an opening that clears the plug's overmould."),
    "audio_jack_3_5mm": ("connectors", "Electronics Parts/Connectors/Audio-connectors/3-5mm-audio-jack.step",
                         "Audio jack, 3.5 mm", E, el("other"), "3.5 mm audio socket.",
                         "Its mouth at a wall with a round opening."),
    "terminal_block_2": ("connectors", "Electronics Parts/Connectors/power-connectors/pcb-terminal-block-female-1x2.step",
                         "Screw terminal block, 2 way", P, el("power"), "PCB screw terminal block.",
                         "Its screws must be reachable with a screwdriver and its wire entries "
                         "face an opening or the open case."),
    "terminal_block_4": ("connectors", "Electronics Parts/Connectors/power-connectors/pcb-terminal-block-female-1x4.step",
                         "Screw terminal block, 4 way", P, el("power"), "PCB screw terminal block.",
                         "Its screws reachable, its wire entries facing an opening."),
    "micro_sd_card": ("connectors", "Computing/Storage/SD/Generic_MICRO_SD_card.step",
                      "Micro-SD card", E, None, "A micro-SD card (the card, for a slot).",
                      "A slot in the wall in line with the card socket, with room for a "
                      "fingertip to push it in and out."),
    # ------------------------------------------------------------ mechanical
    "heatsink_19mm": ("mechanical", "Electronics Parts/Heatsinks/heat-sink-19x19x5mm.step",
                      "Heatsink, 19 × 19 × 5 mm", X, None, "Small finned heatsink.",
                      "Air must pass through its fins: vents in line with them."),
    "nema17_bracket": ("mechanical", "Electrical Parts/Motors/Stepper/NEMA/Nema-17_Mount_Bracket/Nema-17_MountBracket.step",
                       "NEMA 17 mounting bracket", X, None, "L bracket for a NEMA 17 motor.", ""),
}


def _get_json(url):
    import urllib.request
    import simready
    req = urllib.request.Request(url, headers={"User-Agent": "AtechAtelier",
                                               "Accept": "application/vnd.github+json"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=120, context=simready._ssl_context()) as r:
        return json.load(r)


_COMMITS = {}


def _commit(sha):
    if sha not in _COMMITS:
        _COMMITS[sha] = _get_json("https://api.github.com/repos/%s/commits/%s?per_page=300"
                                  % (shelf.REPO, sha))
    return _COMMITS[sha]


def authors(path, rev):
    """Who made the file, oldest first: the authors of every commit that
    added or changed its content, following it back through renames (the
    2026 reorganisation moved most parts; a pure move is not authorship).
    MEASURED 2026-10-29: without following renames, 23 of the curated parts
    named only the person who moved them."""
    names, sha = [], rev                           # oldest first
    for _hop in range(12):
        hist = _get_json("https://api.github.com/repos/%s/commits?sha=%s&path=%s&per_page=100"
                         % (shelf.REPO, sha, urllib.parse.quote(path)))
        if not hist:
            break
        hop, prev = [], None
        for c in reversed(hist):                   # this path's commits, oldest first
            det = _commit(c["sha"])
            f = next((x for x in det.get("files") or [] if x.get("filename") == path), None)
            if f is not None and f.get("status") == "renamed":
                if c is hist[-1]:
                    prev = (f.get("previous_filename"),
                            (det.get("parents") or [{}])[0].get("sha"))
                if not f.get("changes"):
                    continue                       # a pure move
            n = (c.get("commit") or {}).get("author", {}).get("name")
            if n:
                hop.append(n)
        names = hop + names                        # an earlier hop is older
        if not prev or not prev[0] or not prev[1]:
            break
        path, sha = prev
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


PICTURE_PX = (330, 270)       # 1.5 x the dialog's 220 x 180 box


def render_picture(mesh, path):
    """A flat-shaded isometric picture of a mesh (PNG, transparent), drawn
    with QPainter: back faces culled, far triangles first. For the dialog,
    as the library has its own picture for only 3 of the curated parts."""
    import math
    import numpy as np
    from PySide6 import QtCore, QtGui
    if QtGui.QGuiApplication.instance() is None:
        render_picture.app = QtGui.QGuiApplication(["shelf"])
    pts = np.array([[p.x, p.y, p.z] for p in mesh.Points], dtype=float)
    tri = np.array(mesh.Topology[1], dtype=int)
    P = pts - (pts.min(0) + pts.max(0)) / 2.0
    yaw, pitch = math.radians(35.0), math.radians(28.0)
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]) @ np.eye(3)
    R = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ R
    V = P @ R.T                                   # x right, y up, z toward the viewer
    T = V[tri]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = (ln > 1e-12) & (n[:, 2] > 0)
    T, n, ln = T[keep], n[keep], ln[keep]
    n = n / ln[:, None]
    light = np.array([-0.35, 0.55, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(n @ light, 0.0, 1.0)
    order = np.argsort(T[:, :, 2].mean(1))
    w, h = PICTURE_PX
    s = 0.86 * min(w / max(float(np.ptp(V[:, 0])), 1e-9),
                   h / max(float(np.ptp(V[:, 1])), 1e-9))
    img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    base = np.array([96, 126, 160], dtype=float)
    for i in order:
        c = (base * shade[i]).clip(0, 255).astype(int)
        col = QtGui.QColor(int(c[0]), int(c[1]), int(c[2]))
        p.setPen(QtGui.QPen(col, 0.6))
        p.setBrush(col)
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(w / 2 + x * s, h / 2 - y * s)
                                       for x, y, _z in T[i]]))
    p.end()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not img.save(path, "PNG"):
        raise SystemExit("could not write %s" % path)
    return path


def picture_rel(key):
    return "shelf_pictures/%s.png" % key


def refresh_pictures(only=None):
    """SHELF_MODE=pictures (SHELF_ONLY=key,key): download, mesh and draw each part's picture."""
    with open(shelf.INDEX, encoding="utf-8") as fh:
        out = json.load(fh)
    import user_parts
    tmp = tempfile.mkdtemp(prefix="shelf_pic_")
    for key, e in out["parts"].items():
        if only and key not in only:
            continue
        step = shelf.fetch(e["path"], e["git_oid"], e["bytes"],
                           os.path.join(tmp, key + os.path.splitext(e["path"])[1].lower()),
                           out["revision"])
        render_picture(user_parts.read_mesh(step), os.path.join(HERE, picture_rel(key)))
        os.remove(step)
        e["picture"] = picture_rel(key)
        print("%-28s %s" % (key, e["picture"]))
        sys.stdout.flush()
    with open(shelf.INDEX, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print("SHELF_PICTURES=%d" % sum(1 for e in out["parts"].values() if e.get("picture")))


def refresh_authors():
    """SHELF_MODE=authors: re-read only the authors of the parts already indexed."""
    with open(shelf.INDEX, encoding="utf-8") as fh:
        out = json.load(fh)
    for key, e in out["parts"].items():
        e["authors"] = authors(e["path"], out["revision"])
        print("%-28s %s" % (key, ", ".join(e["authors"])))
        sys.stdout.flush()
    with open(shelf.INDEX, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print("SHELF_AUTHORS=%d" % len(out["parts"]))


def main():
    # freecadcmd takes command-line words as its own options: modes come
    # by environment
    mode = os.environ.get("SHELF_MODE", "")
    if mode == "authors":
        return refresh_authors()
    if mode == "pictures":
        return refresh_pictures([k for k in os.environ.get("SHELF_ONLY", "").split(",") if k])
    rev = shelf.REVISION
    tree = _get_json("https://api.github.com/repos/%s/git/trees/%s?recursive=1"
                     % (shelf.REPO, rev))
    if tree.get("truncated"):
        raise SystemExit("the tree listing is truncated")
    blobs = {x["path"]: x for x in tree["tree"] if x["type"] == "blob"}
    out = {"source": "github.com/%s" % shelf.REPO, "revision": rev,
           "licence": shelf.LICENCE, "parts": {}}
    tmp = tempfile.mkdtemp(prefix="shelf_idx_")
    import user_parts
    for key, (group, path, shown, cat, elec, desc, notes) in CURATED.items():
        assert group in dict(shelf.GROUPS), key
        assert cat in user_parts.CATEGORIES, key
        b = blobs.get(path)
        if b is None:
            raise SystemExit("%s: %s is not in the library at %s" % (key, path, rev))
        step = shelf.fetch(path, b["sha"], b["size"],
                           os.path.join(tmp, key + os.path.splitext(path)[1].lower()), rev)
        mesh = user_parts.read_mesh(step)
        bb = mesh.BoundBox
        size = [round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)]
        os.remove(step)
        fc = os.path.splitext(path)[0] + ".FCStd"
        thumb = "thumbnails/" + hashlib.md5(urllib.parse.quote(fc).encode()).hexdigest() + ".png"
        e = {"group": group, "path": path, "git_oid": b["sha"], "bytes": b["size"],
             "display_name": shown, "category": cat, "description": desc,
             "agent_notes": notes, "size_mm": size, "triangles": int(mesh.CountFacets),
             "authors": authors(path, rev),
             "thumb": thumb if thumb in blobs else None}
        if elec:
            e["electrical"] = elec
        out["parts"][key] = e
        print("%-28s %-10s %s %s" % (key, group, size, ", ".join(e["authors"])))
        sys.stdout.flush()
    out["count"] = len(out["parts"])
    with open(shelf.INDEX, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print("SHELF_INDEX=%d" % len(out["parts"]))


main()
