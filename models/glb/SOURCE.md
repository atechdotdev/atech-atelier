# Board and module GLBs

The real Atech models with their materials (black shells, PCBs, gold pins,
clear lids, emissive LEDs, the lit screen), as studio.atech.dev shows them.
`acadagent/board_look.py` draws them in the 3D view, shifted onto the
library STLs by the offsets there. The STLs remain what every fit check
measures.

## Modules (from the atech-module-simready dataset)

Every module except `usb-c.glb` comes from the
[atech-module-simready](https://huggingface.co/datasets/atechdev/atech-module-simready)
dataset (Atech, CC BY 4.0), revision
`0ba167be220e32f61f1fdcada519a65fc7e366e0`, through
`projects/import_simready.py`. `models/SIMREADY.json` records, per module,
the dataset asset, its visual source, and the sha256 of the STL and GLB
written here.

- **Atech CAD** (button, led-grid, temp-sensor, orientation-sensor,
  distance-sensor, dc-motor, screen, speaker, knob, microphone): the dataset
  is built from release v1.7 of `atechdotdev/atech-module-renders`
  (`atech_module_glb.zip`, sha256
  5a6c1de589ec9be4211e997dec2cef61928203f382eba685dd00e4973bcd8c62, folder
  `atech_3d_pkg/glb_plain/`). These GLBs are that release's files, copied
  unchanged after checking each one's sha256 against the one the dataset
  records as its visual source. Compared with v1.5, only `knob.glb` (it now
  has pins, so the knob can be seated) and `screen.glb` (blank display)
  changed.
- **Atech CAD, added 2026-10-28** (big-screen, camera): the same release's
  files, each checked against the sha256 the dataset records as its visual
  source. The SDK has no driver for them yet. `micro-sd.glb` is in the
  release and the dataset but not here: its header cannot be measured
  (`NOT_IMPORTED` in the import script says why).
- **Derived** (pir, scd40-air-quality, robot-arm, stepper-motor,
  soil-sensor, load-cell, power-jack): Atech has no CAD of these modules.
  The dataset builds each from an Atech module shell (button, temp-sensor
  or screen) plus placeholder parts, and the import writes
  these GLBs from the dataset's own meshes. They use plain float32 with no
  quantization, the shell's materials taken from its GLB by name, and the
  MJCF colours for the placeholder parts. They are not Atech CAD of these
  modules, and `presets.yaml` says so (`derived`).

## Board and USB-C

`frame-2.glb` (14-port board) and `usb-c.glb` are from release v1.5 of
`atechdotdev/atech-module-renders` (asset `atech_module_glb.zip`, sha256
4a3112ef2da51cec3b1c85adec407db8912563198524f372dd1cde6cef080e81). Both are
byte-identical in v1.7. The dataset has no USB-C module.

Units: metres, +y up, footprint centre at the origin, the outer
(board-edge) face toward -z.

Licence: see LICENSE-models.md. The dataset publishes the same models
under CC BY 4.0.
