fish_script = """
# Fish mux auto hook
function _mux_auto_hook --on-variable PWD
  if set -q MUX_DEBUG
    echo "[mux debug] Running _mux_auto_hook in $PWD" >&2
  end

  if type -q mux
    set -l commands (mux _internal_auto_update ^/dev/null)
    if test -n "$commands"
      if set -q MUX_DEBUG
        echo "[mux debug] Evaluating commands:" >&2
        echo "$commands" >&2
      end
      eval $commands
    else if set -q MUX_DEBUG
      echo "[mux debug] No env changes from mux." >&2
    end
  else if set -q MUX_DEBUG
    echo "[mux debug] 'mux' not found, skipping." >&2
  end
end

# Add a wrapper function for mux to handle switch command
function mux
  if test "$argv[1]" = "switch"
    set -l output (command mux $argv)
    if test -n "$output"
      eval $output
    end
  else
    command mux $argv
  end
end

_mux_auto_hook
"""


bash_script = """
# Bash mux auto hook
_mux_auto_hook() {
  if [[ -n "$MUX_DEBUG" ]]; then
    echo "[mux debug] Running _mux_auto_hook in $PWD" >&2
  fi

  if ! command -v mux >/dev/null; then
    [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] 'mux' not found, skipping." >&2
    return 1
  fi

  local commands
  if commands="$(mux _internal_auto_update 2>/dev/null)"; then
    if [[ -n "${commands:-}" ]]; then
      [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] Evaluating commands:" >&2 && echo "$commands" >&2
      eval "$commands"
    else
      [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] No env changes from mux." >&2
    fi
  else
    [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] mux _internal_auto_update failed." >&2
    return 1
  fi
}

# Add a wrapper function for mux to handle switch command
mux() {
  if [[ "$1" == "switch" ]]; then
    local output
    output="$(command mux "$@")"
    if [[ -n "$output" ]]; then
      eval "$output"
    fi
  else
    command mux "$@"
  fi
}

_mux_prompt_command_hook() {
  if [[ "$_MUX_IN_PROMPT_COMMAND" != "1" ]]; then
    export _MUX_IN_PROMPT_COMMAND=1
    _mux_auto_hook
    local status=$?
    unset _MUX_IN_PROMPT_COMMAND
    return $status
  fi
  return 0
}

case "$PROMPT_COMMAND" in
  *"_mux_prompt_command_hook"*) : ;;
  *) PROMPT_COMMAND="_mux_prompt_command_hook${PROMPT_COMMAND:+;}${PROMPT_COMMAND}" ;;
esac

[[ -n "$MUX_DEBUG" ]] && echo "[mux debug] Hook added to PROMPT_COMMAND." >&2
_mux_auto_hook
"""


zsh_script = """
# Zsh mux auto hook
_mux_auto_hook() {
  if [[ -n "$MUX_DEBUG" ]]; then
    echo "[mux debug] Running _mux_auto_hook in $PWD" >&2
  fi

  if ! command -v mux >/dev/null; then
    [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] 'mux' not found, skipping." >&2
    return 1
  fi

  local commands
  if commands="$(mux _internal_auto_update 2>/dev/null)"; then
    if [[ -n "${commands:-}" ]]; then
      [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] Evaluating commands:" >&2 && echo "$commands" >&2
      eval "$commands"
    else
      [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] No env changes from mux." >&2
    fi
  else
    [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] mux _internal_auto_update failed." >&2
    return 1
  fi
}

# Add a wrapper function for mux to handle switch command
mux() {
  if [[ "$1" == "switch" ]]; then
    local output
    output="$(command mux "$@")"
    if [[ -n "$output" ]]; then
      eval "$output"
    fi
  else
    command mux "$@"
  fi
}

if (( ${chpwd_functions[(i)_mux_auto_hook]} > ${#chpwd_functions} )); then
  chpwd_functions+=(_mux_auto_hook)
  [[ -n "$MUX_DEBUG" ]] && echo "[mux debug] Hook added to chpwd_functions." >&2
fi

_mux_auto_hook
"""


def get_prompt_script(shell: str) -> str:
    if shell == "fish":
        return fish_script
    elif shell == "bash":
        return bash_script
    elif shell == "zsh":
        return zsh_script
    else:
        raise ValueError(f"Unsupported shell: {shell}")
