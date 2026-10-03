# ---------------------------------------------------------------- agent backend
# Atech Atelier is a desktop app: double-click and everything comes up; close the
# window and nothing is left running. That second half is what this block buys.
#
# It works because the last line of this script is NOT an exec. The bash wrapper
# therefore survives as freecad's PARENT for the whole session (measured: pid
# 2416467 parents 2416477), which is precisely what lets `trap ... EXIT` run
# after freecad returns and reap a child we started. With an exec, bash would be
# replaced and the trap could never fire — the backend would orphan. A systemd
# unit was considered and rejected for the same reason inverted: it outlives the
# app instead of dying with it, and needs a host-side install that breaks the
# single-file product.
#
# opencode is a self-contained ELF, so the PYTHONHOME/PATH surgery above does
# not reach it. It is spawned with an absolute path and an emptied PYTHONHOME so
# it cannot inherit FreeCAD's bundled interpreter.
ATECH_AGENT_HOST="${ATECH_AGENT_HOST:-127.0.0.1}"
ATECH_AGENT_PORT="${ATECH_AGENT_PORT:-4096}"
ATECH_AGENT_BIN="${ATECH_AGENT_BIN:-$HOME/.npm-global/bin/opencode}"
ATECH_AGENT_LOGDIR="${XDG_DATA_HOME:-$HOME/.local/share}/Atech Atelier/v1-1"
ATECH_AGENT_PID=""

# Probe with bash's own /dev/tcp so this needs no python — and NEVER with
# `ss | grep 4096`, because 4096 also appears in the Send-Q column and matches
# unrelated rows, reporting a free port as busy.
atech_port_open() {
    (exec 3<>"/dev/tcp/${ATECH_AGENT_HOST}/${ATECH_AGENT_PORT}") 2>/dev/null
}

atech_cleanup() {
    # Kill ONLY the pid we started, by pid, never by pattern. If we adopted
    # someone else's backend, ATECH_AGENT_PID is empty and we touch nothing.
    if [ -n "$ATECH_AGENT_PID" ] && kill -0 "$ATECH_AGENT_PID" 2>/dev/null; then
        kill -TERM "$ATECH_AGENT_PID" 2>/dev/null
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$ATECH_AGENT_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -0 "$ATECH_AGENT_PID" 2>/dev/null && kill -KILL "$ATECH_AGENT_PID" 2>/dev/null
    fi
}
trap atech_cleanup EXIT INT TERM

# THE SEQUENCING GATE. Autostart stays off until the agent client's message
# parser is fixed and proven. Against a RUNNING backend the current parser reads
# the wrong API schema, turning an immediate honest "backend not reachable" into
# a ~180 s silent stall that then blames a missing API key while the credentials
# are fine. Starting the backend early would make the product look more broken
# and send the fix in the wrong direction. Flip ATECH_AGENT_AUTOSTART_DEFAULT to
# 1 only once that parser has landed.
ATECH_AGENT_AUTOSTART_DEFAULT=0
ATECH_AGENT_AUTOSTART="${ATECH_AGENT_AUTOSTART:-$ATECH_AGENT_AUTOSTART_DEFAULT}"

if atech_port_open; then
    # Something is already listening. AppRun starts nothing, owns nothing and
    # above all kills nothing on exit (ATECH_AGENT_PID stays empty) — but it
    # does NOT say "adopting it" (R134). Whether that listener is adopted is
    # the addon's call, made after it checks who owns it (R105: backend.py
    # _adopt refuses another account's listener, one that fails the health
    # call, or any foreign one under ATECH_AGENT_ADOPT=0). Announcing an
    # adoption here, before that check, contradicted the addon's own notice.
    echo "[atech] ${ATECH_AGENT_HOST}:${ATECH_AGENT_PORT} is already in use; AppRun starts no backend (Atech Atelier checks that listener itself)" >&2
elif [ "$ATECH_AGENT_AUTOSTART" != "0" ] && [ "$ATECH_AGENT_AUTOSTART" != "false" ]; then
    if [ -x "$ATECH_AGENT_BIN" ]; then
        mkdir -p "$ATECH_AGENT_LOGDIR"
        ATECH_AGENT_LOG="${ATECH_AGENT_LOGDIR}/agent-backend.log"
        # A desktop-launched app has no terminal, so output must land somewhere
        # findable or a failure leaves no trace at all.
        {
            echo
            echo "=== $(date '+%Y-%m-%d %H:%M:%S')  AppRun spawn ${ATECH_AGENT_BIN} serve --port ${ATECH_AGENT_PORT} --hostname ${ATECH_AGENT_HOST} ==="
        } >> "$ATECH_AGENT_LOG"
        PYTHONHOME= "$ATECH_AGENT_BIN" serve \
            --port "$ATECH_AGENT_PORT" --hostname "$ATECH_AGENT_HOST" \
            >> "$ATECH_AGENT_LOG" 2>&1 &
        ATECH_AGENT_PID=$!
        echo "[atech] started agent backend pid ${ATECH_AGENT_PID}, log: ${ATECH_AGENT_LOG}" >&2
        # Wait for the PORT, not a fixed sleep: the port answering is the only
        # evidence the process is really serving.
        for _ in $(seq 1 40); do
            atech_port_open && break
            kill -0 "$ATECH_AGENT_PID" 2>/dev/null || {
                echo "[atech] agent backend exited early — see ${ATECH_AGENT_LOG}" >&2
                ATECH_AGENT_PID=""
                break
            }
            sleep 0.25
        done
    else
        echo "[atech] agent autostart requested but ${ATECH_AGENT_BIN} is not executable" >&2
    fi
fi
