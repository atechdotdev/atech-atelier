# ------------------------------------------------- user-data migration (ADR-005)
# FreeCAD names the user's data and config folders after branding.xml's
# ExeName. The product was called "Atech Studio" before 2026-10-03 and is
# "Atech Atelier" now, so without this block an existing user would start with
# an empty profile and their chats, settings and macros would be left behind.
#
# Rules (ADR-005): COPY, never move -- the old folders stay exactly as they
# were, so going back to an older build still works. Only when the NEW folder
# does not exist yet, so a profile the user already has under the new name is
# never overwritten. The copy goes to a temporary name first and is renamed
# into place, so an interrupted copy can never look like a migrated profile.
# Runs before FreeCAD starts, which is the only point at which FreeCAD has not
# yet created the new folders itself.
#
# Inside the COPY (never the old folder) two kinds of string are rewritten in
# user.cfg / system.cfg: absolute paths into the old folders, and the theme
# name, which was renamed with the product ("Atech Studio Light/Dark" ->
# "Atech Atelier Light/Dark"); a profile naming a theme that no longer ships
# would silently lose its colours.
#
# ATECH_MIGRATE=0 turns the block off.
atech_migrate_tree() {  # <old dir> <new dir>; prints what it did
    _old="$1"; _new="$2"
    [ -d "$_old" ] || return 1
    [ -e "$_new" ] && return 1
    _tmp="${_new}.atech-migrating.$$"
    rm -rf "$_tmp"
    mkdir -p "$(dirname "$_new")" 2>/dev/null
    # Copy the CONTENTS ("$_old/."): when the old folder is itself a symlink
    # (dotfile managers do this), `cp -a "$_old"` would copy only the link, and
    # the new name would share -- and the rewrite below edit -- the old profile.
    if mkdir "$_tmp" 2>/dev/null && cp -a "$_old/." "$_tmp/" 2>/dev/null \
       && mv -T "$_tmp" "$_new" 2>/dev/null; then
        echo "[atech] copied your profile: $_old -> $_new (the old folder is kept)" >&2
        return 0
    fi
    rm -rf "$_tmp"
    echo "[atech] could not copy $_old to $_new; starting with a new profile" >&2
    return 1
}

atech_rewrite_file() {  # <file> <from> <to> [<from> <to> ...]
    _f="$1"; shift
    [ -f "$_f" ] || return 0
    # Never write through a link: a symlinked file or folder inside the copy
    # can point back into the old profile, which must stay untouched.
    [ -L "$_f" ] || [ -L "$(dirname "$_f")" ] && return 0
    _txt=""
    IFS= read -r -d '' _txt < "$_f" || true
    _orig="$_txt"
    while [ $# -ge 2 ]; do
        _txt="${_txt//"$1"/"$2"}"
        shift 2
    done
    [ "$_txt" = "$_orig" ] && return 0
    printf '%s' "$_txt" > "$_f.atech-tmp" && mv -f "$_f.atech-tmp" "$_f"
}

if [ "${ATECH_MIGRATE:-1}" != "0" ]; then
    ATECH_OLD_NAME="Atech Studio"
    ATECH_NEW_NAME="Atech Atelier"
    _data="${XDG_DATA_HOME:-$HOME/.local/share}"
    _conf="${XDG_CONFIG_HOME:-$HOME/.config}"
    atech_migrate_tree "$_data/$ATECH_OLD_NAME" "$_data/$ATECH_NEW_NAME"
    _migrated_data=$?
    atech_migrate_tree "$_conf/$ATECH_OLD_NAME" "$_conf/$ATECH_NEW_NAME"
    _migrated_conf=$?
    if [ "$_migrated_data" = 0 ] || [ "$_migrated_conf" = 0 ]; then
        for _cfg in "$_conf/$ATECH_NEW_NAME"/*/user.cfg "$_conf/$ATECH_NEW_NAME"/*/system.cfg \
                    "$_data/$ATECH_NEW_NAME"/*/user.cfg "$_data/$ATECH_NEW_NAME"/*/system.cfg; do
            atech_rewrite_file "$_cfg" \
                "$_data/$ATECH_OLD_NAME/" "$_data/$ATECH_NEW_NAME/" \
                "$_conf/$ATECH_OLD_NAME/" "$_conf/$ATECH_NEW_NAME/" \
                ">$ATECH_OLD_NAME Light<" ">$ATECH_NEW_NAME Light<" \
                ">$ATECH_OLD_NAME Dark<" ">$ATECH_NEW_NAME Dark<"
        done
    fi
    unset _data _conf _migrated_data _migrated_conf _cfg _old _new _tmp _f _txt _orig
fi
