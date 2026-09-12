type InlineErrorProps = {
  message: string | null;
  onDark?: boolean;
};

export function InlineError({ message, onDark = true }: InlineErrorProps) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className={`mt-2 text-sm ${onDark ? "text-error-on-dark" : "text-error"}`}
    >
      {message}
    </p>
  );
}
