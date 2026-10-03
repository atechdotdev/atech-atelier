# FreeCADMCP patches

Applied by `branding/build_appimage.sh` in filename order with `patch -p1`
onto the pristine `addon/` copy. A hunk that does not apply fails the build.

| patch | applied | what |
|---|---|---|
| `0001-rpc-port-setting.patch` | always | `rpc_port` becomes a setting (was hardcoded at three sites); a busy port is reported as an error instead of a Report-View warning; a failed bind leaves no half-initialised server |
| `../optional/0002-rpc-token-origin-host-guard.patch` | only with `--mcp-guard` | every request needs a per-install token (0600 file `freecad_mcp_token` in the user data dir) and is refused when it carries an `Origin` header, a `Content-Type` other than `text/xml`, or a `Host` that is not the loopback address. Tested by `branding/tests/test_mcp_auth.py`. Opt-in because it changes what clients must send, and whether the public build ships the bridge at all is an owner decision (release PRD R10). |

Neither patch turns `auto_start_rpc` on. Upstream's default (`False`) stands.

To regenerate 0001 from a working clone: `git -C tools/freecad-mcp diff <commit> -- addon/`.
