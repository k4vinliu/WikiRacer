import { useEffect, useId, useState } from "react";
import { searchTitles } from "../lib/wikiApi";
import { InlineError } from "./InlineError";

type TitleInputProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error: string | null;
  disabled?: boolean;
  placeholder?: string;
};

export function TitleInput({
  label,
  value,
  onChange,
  error,
  disabled,
  placeholder,
}: TitleInputProps) {
  const id = useId();
  const listId = `${id}-list`;
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    const q = value.trim();
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    const handle = window.setTimeout(() => {
      void searchTitles(q)
        .then(setSuggestions)
        .catch(() => setSuggestions([]));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [value]);

  return (
    <label className="block text-left">
      <span className="text-sm text-text-on-dark-muted">{label}</span>
      <input
        id={id}
        list={listId}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-pill bg-surface-grey px-4 py-2.5 text-text-on-light outline-none placeholder:text-text-on-light-muted disabled:opacity-50"
      />
      <datalist id={listId}>
        {suggestions.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <InlineError message={error} onDark />
    </label>
  );
}
