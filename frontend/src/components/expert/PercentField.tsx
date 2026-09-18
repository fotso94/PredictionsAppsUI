import React from 'react'
import clsx from 'clsx'

/**
 * One probability, entered the way a person says it: 55 means 55 per cent.
 *
 * The old composer asked for 0-1 decimals, so an expert who meant 55% typed 0.55 — and an expert
 * who typed 55 by mistake was told, after pressing publish, that their probabilities summed to
 * 5500%. The unit is now stated twice: in the `%` adornment fixed inside the field, and in the
 * field's accessible name.
 *
 * THERE IS NO PLACEHOLDER NUMBER. A greyed-out "0.50" in an empty box is a suggestion, and a
 * suggestion is exactly what a forecast must not have: the expert's figure has to come from the
 * expert. The box is empty until they type in it.
 */
export interface PercentFieldProps {
  id: string
  label: string
  value: string
  onChange: (next: string) => void
  /** Message to show under the field. Anything non-empty also marks the field invalid. */
  error?: string | null
  /** Shown only when there is no error, so a hint never hides a problem. */
  hint?: string | null
  disabled?: boolean
  /** Adds the required marker and the accessible attribute. Optional fields say "optional". */
  required?: boolean
  className?: string
}

const PercentField: React.FC<PercentFieldProps> = ({
  id, label, value, onChange, error, hint, disabled = false, required = false, className,
}) => {
  const errorId = `${id}-error`
  const hintId = `${id}-hint`
  const describedBy = error ? errorId : hint ? hintId : undefined

  return (
    <div className={clsx('min-w-0', className)}>
      <label htmlFor={id} className="form-label">
        {label}
        {required
          ? <span className="ml-1 text-danger-400" aria-hidden="true">*</span>
          : <span className="ml-1 text-xs font-normal text-secondary-500">(optional)</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          // Text rather than a number input: a number input silently discards what it cannot parse,
          // so "fifty" would vanish as the expert typed it and the form could never explain why.
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={value}
          disabled={disabled}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={event => onChange(event.target.value)}
          className={clsx(
            'form-input num w-full pr-9 disabled:cursor-not-allowed disabled:opacity-60',
            error && 'border-danger-500 focus:ring-danger-500',
          )}
        />
        <span
          className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-secondary-400"
          aria-hidden="true"
        >
          %
        </span>
      </div>
      {error
        ? <p id={errorId} className="form-error">{error}</p>
        : hint
          ? <p id={hintId} className="mt-1 text-xs text-secondary-400">{hint}</p>
          : null}
    </div>
  )
}

export default PercentField
