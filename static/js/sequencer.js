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

  const plan = document.getElementById("render-plan");
  if (plan) {
    const indicator = document.getElementById("render-plan-indicator");
    const upgrade = document.getElementById("render-upgrade");
    const wait = document.getElementById("render-upgrade-wait");
    const note = document.getElementById("render-plan-note");
    const error = document.getElementById("render-plan-error");
    const generateButton = document.getElementById("generate-button");
    let timer = 0;
    let waiting = false;

    const show = (element, visible) => {
      if (element) {
        element.hidden = !visible;
      }
    };

    const apply = (data) => {
      waiting = Boolean(data.switching);
      if (indicator) {
        if (data.tier === "paid") {
          indicator.textContent = "Paid service";
          indicator.className = "badge text-bg-success";
        } else if (data.tier === "free") {
          indicator.textContent = "Free service";
          indicator.className = "badge text-bg-secondary";
        } else {
          indicator.textContent = "Not on Render";
          indicator.className = "badge text-bg-secondary";
        }
      }
      show(wait, waiting);
      show(upgrade, Boolean(upgrade) && data.tier === "free" && !waiting);
      show(note, Boolean(data.returning));
      if (note && data.returning) {
        note.textContent = "Returning to the free service.";
      }
      show(error, Boolean(data.error) && !waiting);
      if (error) {
        error.textContent = data.error || "";
      }
      if (generateButton && !generateButton.dataset.blocked) {
        generateButton.disabled = waiting;
      }
      if (waiting || data.returning) {
        if (!timer) {
          timer = window.setInterval(refresh, 4000);
        }
      } else if (timer) {
        window.clearInterval(timer);
        timer = 0;
      }
    };

    const refresh = () => {
      window.fetch(plan.getAttribute("data-status-url"), {credentials: "same-origin"})
        .then((response) => response.json())
        .then(apply)
        .catch(() => {
          if (!waiting) {
            return;
          }
          show(wait, true);
          if (!timer) {
            timer = window.setInterval(refresh, 4000);
          }
        });
    };

    if (upgrade) {
      upgrade.addEventListener("click", () => {
        waiting = true;
        upgrade.disabled = true;
        show(wait, true);
        show(upgrade, false);
        show(error, false);
        const data = new FormData();
        const csrf = document.querySelector("[name=csrfmiddlewaretoken]");
        if (csrf) {
          data.append("csrfmiddlewaretoken", csrf.value);
        }
        window.fetch(upgrade.getAttribute("data-url"), {
          method: "POST",
          body: data,
          credentials: "same-origin"
        }).then((response) => response.json().then((body) => ({ok: response.ok, body})))
          .then((result) => {
            upgrade.disabled = false;
            if (!result.ok) {
              waiting = false;
              show(wait, false);
              show(upgrade, true);
              show(error, true);
              if (error) {
                error.textContent = result.body.error || "Render did not change the plan.";
              }
              return;
            }
            refresh();
          }).catch(() => {
            upgrade.disabled = false;
            refresh();
          });
      });
    }
    refresh();
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
