# Sesame robot parts (third party)

The files in this folder are parts of the **Sesame Robot** by Dorian Todd
(https://github.com/dorianborian/sesame-robot), taken from the fork
https://github.com/seunyboyxu/New_Spyder at commit
3f76b5f37ac9f9efd3953e50b4beee86e6e88acf, file
`hardware/cad/Sesame-ESP32-v122.step`
(sha256 b6ae8936df90d85d4d6f6b24ea53bd387bd0508da2090fdbc535227d5feb9be0).

Licence: Apache License 2.0 (LICENSE in this folder). They are not covered
by Atech Atelier's own licence.

## Changes made

`projects/import_sesame.py` made these files from the STEP:

- moved the whole assembly into Atech Atelier's frame (Z up, the robot
  facing -Y, the body centred, the lowest foot on z = 0);
- fused each servo's pieces into one solid and left out pieces under
  100 mm³ (case screw heads, the label film, cable stubs);
- saved one gzip-compressed BREP per part.

The shapes are otherwise unchanged. The servos are the SG90 models the
upstream CAD uses; the build uses MG90S servos of the same outline.

`top_cover.brep.gz` is the original top cover, kept for comparison. The
"Sesame with Atech" example replaces it with a new deck and lid that hold
the Atech board and the Atech screen.
