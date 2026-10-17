document.addEventListener("submit", (event) => {
  const message = event.target.getAttribute("data-confirm");
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const enforcement = document.querySelector("[name=enforcement]");
  const severity = document.getElementById("severity-field");
  const payloadWarning = document.getElementById("payload-soft-warning");
  const operator = document.querySelector("[name=operator]");
  const valueField = document.getElementById("value-field");
  const valueToField = document.getElementById("value-to-field");
  const selector = document.querySelector("[name=selector]");

  const sync = () => {
    const soft = enforcement && enforcement.value === "soft";
    if (severity) {
      severity.hidden = !soft;
    }
    if (payloadWarning) {
      payloadWarning.hidden = !soft;
    }
    const operatorValue = operator ? operator.value : "";
    if (valueField) {
      valueField.hidden = operatorValue === "is_blank" || operatorValue === "is_not_blank";
    }
    if (valueToField) {
      valueToField.hidden = operatorValue !== "between";
    }
    document.querySelectorAll("[data-selector]").forEach((element) => {
      element.hidden = !selector || element.getAttribute("data-selector") !== selector.value;
    });
  };

  [enforcement, operator, selector].forEach((element) => {
    if (element) {
      element.addEventListener("change", sync);
    }
  });
  sync();
});
