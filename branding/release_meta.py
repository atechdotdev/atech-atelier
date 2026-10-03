#!/usr/bin/env python3
"""One version, stamped everywhere (release PRD R39).

VERSION at the repository root is the single source (ADR-006: 0.1.0 is the
first public preview). build_appimage.sh stamps it into:

    the output file name          AtechAtelier-<version>-x86_64.AppImage
    both .desktop files           X-AppImage-Version=<version>
    the AppStream metainfo        <releases><release version= date=/></releases>
    ATECH_CHANGES.txt             "Version <version>"

and verify_tree.py checks, inside the built image, that all of them agree.

The value is the OWNER's (ADR-006). This script reads it and never writes it.

    python3 branding/release_meta.py version
    python3 branding/release_meta.py outname [arch]
    python3 branding/release_meta.py desktop  <file> <version>
    python3 branding/release_meta.py metainfo <file> <version> <YYYY-MM-DD>
    python3 branding/release_meta.py screenshots <file> [url ...]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The repository root's VERSION (ADR-006). branding/VERSION, the earlier
# copy, is retired: two version files can disagree, one cannot.
VERSION_FILE = os.path.join(os.path.dirname(HERE), "VERSION")
MARKER = "<!--RELEASES-->"
SCREENSHOTS_MARKER = "<!--SCREENSHOTS-->"
PRODUCT = "Atech Atelier"
FILE_STEM = "AtechAtelier"

# Semantic-version shape; AppStream and AppImage both take free text, but a
# version that sorts is the only kind an updater can compare.
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_version(path=VERSION_FILE):
    with open(path, encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()
                 and not ln.lstrip().startswith("#")]
    if len(lines) != 1 or not _VERSION.match(lines[0]):
        raise ValueError("%s must hold exactly one version like 1.2.3, got %r"
                         % (path, lines))
    return lines[0]


def out_name(version, arch="x86_64"):
    return "%s-%s-%s.AppImage" % (FILE_STEM, version, arch)


def stamp_desktop(text, version):
    """Set X-AppImage-Version in the [Desktop Entry] group."""
    if not _VERSION.match(version):
        raise ValueError("bad version %r" % version)
    lines = text.rstrip("\n").split("\n")
    if not lines or lines[0].strip() != "[Desktop Entry]":
        raise ValueError("not a desktop entry (first line %r)" % lines[:1])
    # End of the [Desktop Entry] group: the next group header, or EOF.
    end = next((i for i, ln in enumerate(lines[1:], 1)
                if ln.startswith("[")), len(lines))
    body = [ln for ln in lines[1:end] if not ln.startswith("X-AppImage-Version=")]
    body.append("X-AppImage-Version=%s" % version)
    return "\n".join([lines[0]] + body + lines[end:]) + "\n"


def stamp_metainfo(xml, version, date):
    if not _VERSION.match(version):
        raise ValueError("bad version %r" % version)
    if not _DATE.match(date):
        raise ValueError("bad date %r (want YYYY-MM-DD)" % date)
    if xml.count(MARKER) != 1:
        raise ValueError("metainfo template must contain %s exactly once" % MARKER)
    block = ('<releases>\n'
             '    <release version="%s" date="%s">\n'
             '      <description>\n'
             '        <p>%s %s, a preview release.</p>\n'
             '      </description>\n'
             '    </release>\n'
             '  </releases>' % (version, date, PRODUCT, version))
    return xml.replace(MARKER, block)


_URL = re.compile(r"^https://[^\s<>\"']+\.(?:png|jpg|jpeg)$")


def stamp_screenshots(xml, urls):
    """Replace the screenshots marker.

    With URLs: one <screenshot> each, the first marked default. Without: a
    comment saying plainly that none is published. No URL is ever invented
    here -- a screenshot link that does not resolve is a broken store page
    (and a P1 number in XML form)."""
    if xml.count(SCREENSHOTS_MARKER) != 1:
        raise ValueError("metainfo template must contain %s exactly once"
                         % SCREENSHOTS_MARKER)
    for u in urls:
        if not _URL.match(u):
            raise ValueError("screenshot url must be https://...png|jpg, got %r" % u)
    if not urls:
        block = ("<!-- SCREENSHOTS: PLACEHOLDER. None published yet; set "
                 "ATECH_SCREENSHOT_URLS at build time once the images are "
                 "hosted. -->")
    else:
        items = []
        for i, u in enumerate(urls):
            items.append('    <screenshot%s>\n      <image>%s</image>\n'
                         '    </screenshot>' % (' type="default"' if i == 0 else "", u))
        block = "<screenshots>\n%s\n  </screenshots>" % "\n".join(items)
    return xml.replace(SCREENSHOTS_MARKER, block)


def _rewrite(path, fn, *args):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(fn(src, *args))


def main(argv):
    try:
        if argv == ["version"]:
            print(read_version())
        elif argv[:1] == ["outname"] and len(argv) <= 2:
            print(out_name(read_version(), *argv[1:]))
        elif argv[:1] == ["desktop"] and len(argv) == 3:
            _rewrite(argv[1], stamp_desktop, argv[2])
        elif argv[:1] == ["metainfo"] and len(argv) == 4:
            _rewrite(argv[1], stamp_metainfo, argv[2], argv[3])
        elif argv[:1] == ["screenshots"] and len(argv) >= 2:
            _rewrite(argv[1], stamp_screenshots, argv[2:])
        else:
            sys.stderr.write(__doc__)
            return 2
    except (OSError, ValueError) as e:
        sys.stderr.write("release_meta: %s\n" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
