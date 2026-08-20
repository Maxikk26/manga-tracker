import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DecimalInput, sanitizeDecimal } from "./DecimalInput";

/** The component is controlled, so keystroke tests need a real state owner. */
function Harness({ disabled = false }: { disabled?: boolean }) {
  const [value, setValue] = useState("");
  return <DecimalInput value={value} onChange={setValue} disabled={disabled} />;
}

const input = () => screen.getByRole("textbox") as HTMLInputElement;

describe("sanitizeDecimal", () => {
  it.each([
    ["0170", "170"], // the owner's original complaint, impossible by construction
    ["00.5", "0.5"],
    ["0", "0"],
    ["0.5", "0.5"],
    ["170.05", "170.05"],
    ["1.2.3", "1.23"], // one dot, ever
    ["1a2b3", "123"],
    ["-1", "1"], // no signs: positive decimals only
    ["1e5", "15"], // no exponents either
    ["", ""],
    [".", "."], // legal intermediate draft while typing ".5"
  ])("%j -> %j", (raw, expected) => {
    expect(sanitizeDecimal(raw)).toBe(expected);
  });
});

describe("DecimalInput", () => {
  it("is a text input with the decimal keyboard and no spinner role", () => {
    render(<Harness />);

    expect(input()).toHaveAttribute("type", "text");
    expect(input()).toHaveAttribute("inputmode", "decimal");
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it('typing into the empty field yields "170", never "0170"', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(input()).toHaveAttribute("placeholder", "0");
    await user.type(input(), "170");

    expect(input().value).toBe("170");
  });

  it("accepts a decimal like 170.05", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(input(), "170.05");

    expect(input().value).toBe("170.05");
  });

  it("ignores letters and a second dot at the keystroke", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(input(), "1a7x0..5");

    expect(input().value).toBe("170.5");
  });

  it("stays empty when only rejected characters are typed", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(input(), "abc-");

    expect(input().value).toBe("");
  });

  it("respects disabled", () => {
    render(<Harness disabled />);

    expect(input()).toBeDisabled();
  });
});
