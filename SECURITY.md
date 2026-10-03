# Security policy

## Supported versions

Atech Atelier is a preview. Only the latest release gets fixes.

| version | supported |
|---|---|
| latest 0.x release | yes |
| anything older | no |

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub: open the repository's **Security** tab
and choose **Report a vulnerability**. Only the maintainers can see the
report.

Include:

- the Atech Atelier version (it is in the AppImage file name)
- what you did, what happened, and what you expected
- whether the problem needs a malicious file, a malicious network peer, or
  only local access

We will acknowledge the report, tell you whether we can reproduce it, and
agree a disclosure date with you before anything is published.

## What is in scope

- the Atech workbench (`addon/AcadAgent/`): the chat panel, the agent
  sandbox, and how it runs scripts the agent writes
- the build and packaging (`branding/`), including the AppRun changes
- the bundled FreeCAD MCP bridge as patched by Atech
  (`branding/vendor/freecad-mcp/`)

## What is out of scope

- FreeCAD itself and the libraries it bundles. Report those to the
  [FreeCAD project](https://github.com/FreeCAD/FreeCAD/security) or to the
  library's own maintainers. Atech Atelier ships the official FreeCAD 1.1.3
  image unmodified, so a FreeCAD fix reaches us through a FreeCAD release.
- Claude Code, the agent engine the chat uses. It is installed and updated
  separately by the user. Report problems in it to Anthropic.

## How the agent runs code

The chat agent writes Python scripts that FreeCAD runs on your machine.
Treat a design conversation like running a script you were sent: the
workbench runs agent builds in a sandbox where one is available, but you
should not point the agent at files or folders you would not hand to a
script.
