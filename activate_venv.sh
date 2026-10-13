# Source this from the project folder: source ./activate_venv.sh
# Bash and zsh are supported; executing it cannot change a parent shell.
if [ -z "${BASH_VERSION:-}" ] && [ -z "${ZSH_VERSION:-}" ]; then
    printf '%s\n' 'Use source ./activate_venv.sh in Bash or zsh.' >&2
    return 1 2>/dev/null || exit 1
fi
if [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]}" = "$0" ]; then
    printf '%s\n' 'Use: source ./activate_venv.sh (from the project folder).' >&2
    exit 1
fi
if [ -n "${ZSH_VERSION:-}" ]; then
    case "$ZSH_EVAL_CONTEXT" in
        *:file) ;;
        *) printf '%s\n' 'Use: source ./activate_venv.sh (from the project folder).' >&2; exit 1 ;;
    esac
fi
if [ ! -f .venv/bin/activate ] || [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'ERROR: The environment is missing. Run source ./setup_venv.sh first.' >&2
    return 1 2>/dev/null || exit 1
fi
if ! . .venv/bin/activate; then
    printf '%s\n' 'ERROR: Could not activate .venv. Recreate it with setup_venv.sh.' >&2
    return 1 2>/dev/null || exit 1
fi
printf '%s\n' '.venv is activated in this terminal. Run: python analyse_example.py'
