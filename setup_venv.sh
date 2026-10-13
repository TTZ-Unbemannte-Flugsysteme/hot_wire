# Source this from the project folder: source ./setup_venv.sh [daq]
# Sourcing lets activation remain in the current Bash/zsh terminal.
if [ -z "${BASH_VERSION:-}" ] && [ -z "${ZSH_VERSION:-}" ]; then
    printf '%s\n' 'Use source ./setup_venv.sh in Bash or zsh.' >&2
    return 1 2>/dev/null || exit 1
fi
if [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
    printf '%s\n' 'Use: source ./setup_venv.sh (from the project folder).' >&2
    exit 1
fi
if [ -n "${ZSH_VERSION:-}" ]; then
    case "$ZSH_EVAL_CONTEXT" in
        *:file) ;;
        *) printf '%s\n' 'Use: source ./setup_venv.sh (from the project folder).' >&2; exit 1 ;;
    esac
fi

_hotwire_setup() {
    local task_requirements=requirements.txt task_python=python3 task_option task_check_option=
    if [ "$(id -u)" = 0 ]; then
        printf '%s\n' 'ERROR: Run Python package setup as your normal user, without sudo.' \
            'For the separate system driver, use: python install_ni_driver.py after setup with daq.' >&2
        return 1
    fi
    for task_option in "$@"; do
        case "$task_option" in
            daq) task_requirements=requirements-daq.txt; task_check_option=--daq ;;
            *) printf 'ERROR: Unknown setup option: %s\n' "$task_option" >&2; return 1 ;;
        esac
    done
    if [ ! -f user_settings.json ] || [ ! -f "$task_requirements" ] || [ ! -f activate_venv.sh ]; then
        printf '%s\n' 'ERROR: Run source ./setup_venv.sh from the downloaded project folder.' >&2
        return 1
    fi
    if command -v python3.13 >/dev/null 2>&1; then
        task_python=python3.13
    fi
    if ! "$task_python" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
        printf '%s\n' 'ERROR: Install Python 3.10 or newer; Python 3.13 is recommended.' >&2
        return 1
    fi
    if [ ! -x .venv/bin/python ]; then
        printf '%s\n' 'Creating the virtual environment in .venv ...'
        if ! "$task_python" -m venv .venv; then
            printf '%s\n' 'ERROR: Could not create .venv. On Linux, check that python3-venv is installed.' >&2
            return 1
        fi
    fi
    if ! .venv/bin/python -c 'import sys; print("Using Python", sys.version.split()[0]); sys.exit(sys.version_info < (3, 10))'; then
        printf '%s\n' 'ERROR: The existing .venv needs Python 3.10 or newer. See README.md.' >&2
        return 1
    fi
    if ! .venv/bin/python -m pip install --upgrade pip || ! .venv/bin/python -m pip install -r "$task_requirements"; then
        printf '%s\n' 'ERROR: Installing packages failed. Check the internet connection and the messages above.' >&2
        return 1
    fi
    if [ ! -f user_settings.local.json ]; then
        if ! cp user_settings.json user_settings.local.json; then
            printf '%s\n' 'ERROR: Could not create user_settings.local.json.' >&2
            return 1
        fi
    fi
    if ! .venv/bin/python check_setup.py ${task_check_option:+"$task_check_option"}; then
        printf '%s\n' 'ERROR: Setup checks failed. Fix the errors above and run setup again.' >&2
        return 1
    fi
    printf '%s\n' 'Setup finished. Edit user_settings.local.json for your own settings.'
    if [ "$task_requirements" = requirements-daq.txt ]; then
        printf '%s\n' 'DAQ Python package installed. The NI system driver is a separate installation.' \
            'On Windows/native Linux, run: python install_ni_driver.py' \
            'WSL is used here for analysis; use a Windows or native Linux checkout for recording.'
    fi
    . ./activate_venv.sh
}

if _hotwire_setup "$@"; then
    unset -f _hotwire_setup
else
    unset -f _hotwire_setup
    return 1 2>/dev/null || exit 1
fi
