document.addEventListener("submit", (event) => {
  const message = event.target.getAttribute("data-confirm");
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const generateForm = document.getElementById("generate-form");
  if (generateForm) {
    generateForm.addEventListener("submit", (event) => {
      if (generateForm.dataset.running === "1") {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      generateForm.dataset.running = "1";
      const progress = document.getElementById("generate-progress");
      const button = document.getElementById("generate-button");
      const cancelButton = document.getElementById("generate-cancel");
      const token = String(Date.now());
      if (progress) {
        progress.hidden = false;
      }
      if (button) {
        button.disabled = true;
      }
      if (cancelButton) {
        cancelButton.hidden = false;
        cancelButton.onclick = () => {
          cancelButton.disabled = true;
          const data = new FormData();
          const csrf = generateForm.querySelector("[name=csrfmiddlewaretoken]");
          if (csrf) {
            data.append("csrfmiddlewaretoken", csrf.value);
          }
          data.append("cancel_token", token);
          window.fetch(cancelButton.getAttribute("data-url"), {
            method: "POST",
            body: data,
            credentials: "same-origin"
          });
        };
      }
      const body = new FormData(generateForm);
      body.append("async", "1");
      body.append("cancel_token", token);
      window.fetch(generateForm.action || window.location.href, {
        method: "POST",
        body: body,
        credentials: "same-origin"
      }).then((response) => response.json()).then((data) => {
        window.location = data.redirect;
      }).catch(() => {
        window.location.reload();
      });
    });
  }
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
