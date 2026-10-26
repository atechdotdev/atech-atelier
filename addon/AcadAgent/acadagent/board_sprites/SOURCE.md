# Board sprites

Plan-view pictures of the Atech board and modules, the same ones
studio.atech.dev draws its board from. Copied unchanged from the studio
repository, `p2p/board_sprites/` at commit 80dc8ca2cdda.
`MANIFEST.json` (studio's own) records each file's sha256, its scale
(8 px/mm), the source GLB it was rendered from, and `origin_px`: where the
module's connector centre (the port it seats on) is in the picture.

Orientation: image right = +x, image up = -z. The board is drawn as it sits
in the board frame. Each module is drawn with its outer face up.

They are renders of the Atech board and module 3D models, so they carry the
models' licence: CC BY-NC 4.0 (LICENSE-models.md).

`modules_page.BoardMap` draws them.
