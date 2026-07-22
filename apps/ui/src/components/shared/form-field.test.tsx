import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Input } from "@/components/ui/input";
import { FormField } from "./form-field";

describe("FormField", () => {
  it("renders the label and wires it to the input via htmlFor/id", () => {
    render(
      <FormField label="Stripe key">
        {(id) => <Input id={id} defaultValue="pk_test_123" />}
      </FormField>,
    );
    const input = screen.getByLabelText("Stripe key");
    expect(input).toBeInTheDocument();
  });

  it("renders the hint when no error is set", () => {
    render(
      <FormField label="Name" hint="This is shown on invoices.">
        {(id) => <Input id={id} />}
      </FormField>,
    );
    expect(
      screen.getByText("This is shown on invoices."),
    ).toBeInTheDocument();
  });

  it("prefers the error message over the hint when both are set", () => {
    render(
      <FormField
        label="Name"
        hint="This is shown on invoices."
        error="Name is required"
      >
        {(id) => <Input id={id} />}
      </FormField>,
    );
    expect(screen.getByText("Name is required")).toBeInTheDocument();
    expect(
      screen.queryByText("This is shown on invoices."),
    ).not.toBeInTheDocument();
  });
});
