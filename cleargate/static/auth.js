(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const steps = {
    login: $("#step-login"),
    signup: $("#step-signup"),
    email: $("#step-email"),
    reset: $("#step-reset"),
    done: $("#step-done"),
  };
  let resetToken = null;

  function show(name) {
    for (const [k, el] of Object.entries(steps)) el.hidden = k !== name;
    document.querySelectorAll(".form-error").forEach((e) => (e.textContent = ""));
    const first = steps[name].querySelector("input:not([type=checkbox])");
    if (first) first.focus();
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    return data;
  }

  // Wrap a submit handler: disables the button, shows errors under the form.
  function onSubmit(form, fn) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $(".form-error", form);
      const btn = $("button[type=submit]", form);
      err.textContent = "";
      btn.disabled = true;
      try {
        await fn();
      } catch (ex) {
        err.textContent = ex.message;
      } finally {
        btn.disabled = false;
      }
    });
  }

  document.querySelectorAll("[data-goto]").forEach((b) =>
    b.addEventListener("click", () => show(b.dataset.goto))
  );

  // Step 1 - sign in
  onSubmit(steps.login, async () => {
    await post("/api/login", {
      identifier: $("#identifier").value,
      password: $("#password").value,
      remember: $("#remember").checked,
    });
    location.href = "/portal";
  });

  onSubmit(steps.signup, async () => {
    const password = $("#signup-password").value;
    if (password !== $("#signup-confirm").value) {
      throw new Error("The passwords don't match.");
    }
    await post("/api/signup", {
      student_no: $("#signup-student-no").value,
      email: $("#signup-email").value,
      name: $("#signup-name").value,
      course_year: $("#signup-course").value,
      academic_year: $("#signup-year").value,
      password,
    });
    location.href = "/portal";
  });

  // Step 2 - request + verify code
  $("#send-code").addEventListener("click", async () => {
    const err = $(".form-error", steps.email);
    const hint = $("#code-hint");
    err.textContent = "";
    const email = $("#fp-email").value.trim();
    if (!email) {
      err.textContent = "Enter your student email first.";
      return;
    }
    try {
      await post("/api/forgot/request", { email });
      hint.hidden = false;
      hint.textContent = "If that email is registered, a 6-digit code was generated and is valid for 10 minutes.";
      $("#fp-code").focus();
    } catch (ex) {
      err.textContent = ex.message;
    }
  });

  onSubmit(steps.email, async () => {
    const email = $("#fp-email").value.trim();
    const code = $("#fp-code").value.trim();
    if (!email || !code) throw new Error("Enter your email and the verification code.");
    const data = await post("/api/forgot/verify", { email, code });
    resetToken = data.token;
    show("reset");
  });

  // Step 3 - new password
  onSubmit(steps.reset, async () => {
    const p1 = $("#np1").value;
    const p2 = $("#np2").value;
    if (p1.length < 8) throw new Error("Use at least 8 characters for your new password.");
    if (p1 !== p2) throw new Error("The two passwords don't match.");
    await post("/api/forgot/reset", { token: resetToken, password: p1 });
    resetToken = null;
    show("done");
  });

  // Step 4 - done
  $("#go-main").addEventListener("click", () => (location.href = "/portal"));
})();
