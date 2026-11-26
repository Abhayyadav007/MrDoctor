(() => {
  const role = document.getElementById("id_role");
  const login = document.getElementById("id_login");
  const label = login ? document.querySelector(`label[for="${login.id}"]`) : null;
  const googleLoginOption = document.getElementById("google-login-option");
  if (!role || !login || !label) return;

  const updateLoginHint = () => {
    const patient = role.value === "PATIENT";
    if (googleLoginOption) googleLoginOption.hidden = !patient;
    label.textContent = patient ? "Email address" : "Username";
    login.placeholder = patient ? "Email address" : "Username";
    login.autocomplete = patient ? "email" : "username";
    login.type = patient ? "email" : "text";
  };
  role.addEventListener("change", updateLoginHint);
  updateLoginHint();
})();
