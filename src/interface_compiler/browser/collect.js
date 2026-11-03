// In-page facts for one document. facts.py evaluates this file and reads the
// returned JSON. Elements are rows aligned with `fields` so a large page does
// not repeat every key. Accessibility roles are overlaid in Python; the roles
// recorded here are the HTML ones, which the skeleton path must keep (a summary
// stays button even when Chromium later reports DisclosureTriangle).
(() => {
  const SELECTOR = [
    "a[href]",
    "button",
    "input",
    "select",
    "textarea",
    "option",
    "summary",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "nav",
    "main",
    "footer",
    "aside",
    "form",
    "dialog",
    "details",
    "[role]",
    "[aria-label]",
    "[aria-labelledby]",
  ].join(",");

  // Form controls are exposed as named properties and hide these.
  const readId = Object.getOwnPropertyDescriptor(Element.prototype, "id").get;
  const readFormAction = Object.getOwnPropertyDescriptor(HTMLFormElement.prototype, "action").get;

  function elementId(el) {
    return readId.call(el) || "";
  }

  function elementMatches(el, selector) {
    return Element.prototype.matches.call(el, selector);
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function hidesText(el) {
    if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") {
      return true;
    }
    const known = displayNone.get(el);
    if (known !== undefined) {
      return known === true;
    }
    return getComputedStyle(el).display === "none";
  }

  function ownText(el) {
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        text += ` ${node.textContent}`;
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName;
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON") {
          continue;
        }
        if (hidesText(node)) {
          continue;
        }
        if (tag === "IMG") {
          text += ` ${node.getAttribute("alt") || ""}`;
          continue;
        }
        text += ` ${ownText(node)}`;
      }
    }
    return clean(text);
  }

  function accName(el) {
    const labelled = clean(el.getAttribute("aria-label"));
    if (labelled) {
      return labelled;
    }
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const parts = [];
      for (const id of labelledBy.split(/\s+/)) {
        if (!id) {
          continue;
        }
        const target = document.getElementById(id);
        if (target) {
          parts.push(ownText(target) || clean(target.textContent));
        }
      }
      const joined = clean(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    return clean(el.getAttribute("title"));
  }

  // Filled once per collection. The element walk must not rescan the document.
  let labelsByFor = new Map();
  let idCounts = new Map();
  let nameCounts = new Map();
  let nthOfType = new Map();
  let legendText = new Map();
  let formIndexes = new Map();
  let flagHidden = new Map();
  let flagAriaHidden = new Map();
  let flagInert = new Map();
  let flagAriaDisabled = new Map();
  let styleHidden = new Map();
  let displayNone = new Map();

  function labelFor(el) {
    const id = elementId(el);
    if (!id) {
      return null;
    }
    return labelsByFor.get(id) || null;
  }

  function labelText(el) {
    const explicit = labelFor(el);
    if (explicit) {
      const text = ownText(explicit);
      if (text) {
        return text;
      }
    }
    const wrapping = el.closest("label");
    if (wrapping && wrapping !== el) {
      const text = ownText(wrapping);
      if (text) {
        return text;
      }
    }
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const parts = [];
      for (const id of labelledBy.split(/\s+/)) {
        const target = id ? document.getElementById(id) : null;
        if (target) {
          parts.push(ownText(target) || clean(target.textContent));
        }
      }
      const joined = clean(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    const placeholder = clean(el.getAttribute("placeholder"));
    if (placeholder) {
      return placeholder;
    }
    // A submit value is its name. The fieldset legend must not replace it.
    if (el.tagName === "INPUT") {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (type === "submit" || type === "reset" || type === "button") {
        const value = clean(el.value);
        if (value) {
          return value;
        }
      }
      if (type === "image") {
        const alt = clean(el.getAttribute("alt"));
        if (alt) {
          return alt;
        }
      }
    }
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const text = legendText.get(fieldset) || "";
      if (text) {
        return text;
      }
    }
    return "";
  }

  function elementRole(el) {
    const explicit = clean(el.getAttribute("role")).split(" ")[0];
    if (explicit) {
      return explicit;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) {
      return "link";
    }
    if (tag === "button" || tag === "summary") {
      return "button";
    }
    if (tag === "select") {
      return el.multiple ? "listbox" : "combobox";
    }
    if (tag === "textarea") {
      return "textbox";
    }
    if (tag === "option") {
      return "option";
    }
    if (/^h[1-6]$/.test(tag)) {
      return "heading";
    }
    if (tag === "header") {
      return "banner";
    }
    if (tag === "nav") {
      return "navigation";
    }
    if (tag === "main") {
      return "main";
    }
    if (tag === "footer") {
      return "contentinfo";
    }
    if (tag === "aside") {
      return "complementary";
    }
    if (tag === "form") {
      return "form";
    }
    if (tag === "dialog") {
      return "dialog";
    }
    if (tag === "details") {
      return "group";
    }
    if (tag === "section") {
      return accName(el) ? "region" : "generic";
    }
    if (tag === "input") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") {
        return "checkbox";
      }
      if (type === "radio") {
        return "radio";
      }
      if (type === "range") {
        return "slider";
      }
      if (type === "number") {
        return "spinbutton";
      }
      if (type === "search") {
        return "searchbox";
      }
      // Chromium reports these as button. The HTML role matches, so the tail
      // kept after the overlay stops is not relabeled.
      if (type === "button" || type === "submit" || type === "reset" || type === "image") {
        return "button";
      }
      // Chromium's node role is button (the chooser). The fact keeps file so
      // an upload is not stored as a button when the overlay does run.
      if (type === "file") {
        return "file";
      }
      return "textbox";
    }
    return "generic";
  }

  function landmarkRole(el) {
    const explicit = clean(el.getAttribute("role")).split(" ")[0];
    const tag = el.tagName;
    if ((tag === "HEADER" || tag === "FOOTER") && !explicit && el.parentElement !== document.body) {
      return null;
    }
    const role = elementRole(el);
    if (
      role === "banner" ||
      role === "navigation" ||
      role === "main" ||
      role === "contentinfo" ||
      role === "complementary" ||
      role === "search"
    ) {
      return role;
    }
    if ((role === "form" || role === "region") && accName(el)) {
      return role;
    }
    return null;
  }

  function landmarkOf(el) {
    let node = el.parentElement;
    while (node && node !== document.documentElement) {
      const role = landmarkRole(node);
      if (role) {
        const name = accName(node);
        return name ? `${role} ${name}` : role;
      }
      node = node.parentElement;
    }
    return "";
  }

  function fallbackName(el) {
    const named = accName(el);
    if (named) {
      return named;
    }
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      return labelText(el);
    }
    return ownText(el) || labelText(el);
  }

  function groupKey(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (el.tagName === "INPUT" && type === "radio") {
      const name = el.getAttribute("name");
      if (name) {
        return name;
      }
    }
    const radioGroup = el.closest("[role='radiogroup']");
    if (radioGroup) {
      const name = accName(radioGroup) || elementId(radioGroup);
      if (name) {
        return name;
      }
    }
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const text = legendText.get(fieldset) || "";
      if (text) {
        return text;
      }
    }
    if (el.hasAttribute("aria-pressed")) {
      const toolbar = el.closest("[role='toolbar']");
      if (toolbar) {
        return accName(toolbar) || elementId(toolbar) || null;
      }
    }
    return null;
  }

  function cssOf(el) {
    const id = elementId(el);
    if (id && idCounts.get(id) === 1) {
      return `#${CSS.escape(id)}`;
    }
    const name = el.getAttribute("name");
    if (name && /^[A-Za-z0-9_-]+$/.test(name)) {
      const key = `${el.tagName.toLowerCase()}\n${name}`;
      if (nameCounts.get(key) === 1) {
        return `${el.tagName.toLowerCase()}[name="${name}"]`;
      }
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node.tagName !== "HTML") {
      if (node.tagName === "BODY") {
        parts.unshift("body");
        break;
      }
      const nth = nthOfType.get(node) || 1;
      parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${nth})`);
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function skeletonOf(el) {
    const chain = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && node !== document.documentElement) {
      chain.unshift(node);
      node = node.parentElement;
    }
    const parts = [];
    if (document.body) {
      parts.push(`body|${elementRole(document.body)}`);
    }
    for (const item of chain) {
      parts.push(`${item.tagName.toLowerCase()}|${elementRole(item)}`);
    }
    return parts.join(" > ");
  }

  function expanded(el) {
    const value = el.getAttribute("aria-expanded");
    if (value !== null) {
      return value;
    }
    if (el.tagName === "DETAILS") {
      return el.open ? "true" : "false";
    }
    if (el.tagName === "SUMMARY" && el.parentElement && el.parentElement.tagName === "DETAILS") {
      return el.parentElement.open ? "true" : "false";
    }
    return null;
  }

  function optionsOf(el) {
    if (el.tagName === "SELECT") {
      return Array.from(el.options, (opt) => ({
        value: opt.value,
        label: clean(opt.label),
        disabled: optionDisabled(opt),
      }));
    }
    let box = el.getAttribute("role") === "listbox" ? el : null;
    if (!box) {
      const controls = el.getAttribute("aria-controls");
      const id = controls ? controls.split(/\s+/).find(Boolean) : "";
      const target = id ? document.getElementById(id) : null;
      if (target && (target.getAttribute("role") === "listbox" || target.querySelector("[role='option']"))) {
        box = target;
      }
    }
    if (!box) {
      return [];
    }
    return Array.from(box.querySelectorAll("[role='option']"), (opt) => ({
      value: opt.getAttribute("data-value") || ownText(opt),
      label: ownText(opt),
      disabled: optionDisabled(opt),
    }));
  }

  function isVisible(el, rect) {
    if (flagHidden.get(el) === true || styleHidden.get(el) === true) {
      return false;
    }
    return rect.width > 0 && rect.height > 0;
  }

  // Off-screen centres are not a hit test. A viewport centre is covered when
  // the top element is neither this node nor something inside it.
  function isCovered(el, rect, visible) {
    if (!visible) {
      return false;
    }
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (cx < 0 || cy < 0 || cx >= window.innerWidth || cy >= window.innerHeight) {
      return false;
    }
    const hit = document.elementFromPoint(cx, cy);
    if (!hit) {
      return true;
    }
    return hit !== el && !el.contains(hit);
  }

  function inViewport(rect) {
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.right > 0 &&
      rect.top < window.innerHeight &&
      rect.left < window.innerWidth
    );
  }

  // IDL minLength/maxLength is -1 when the attribute is absent or invalid.
  // Chrome's reflection parses " 3 " as 3 and "1.5" as 1.
  function reflectedLength(value) {
    if (typeof value !== "number" || value < 0) {
      return null;
    }
    return value;
  }

  function constraintsOf(el) {
    return {
      required: el.required === true,
      pattern: el.getAttribute("pattern"),
      min: el.getAttribute("min"),
      max: el.getAttribute("max"),
      step: el.getAttribute("step"),
      minlength: reflectedLength(el.minLength),
      maxlength: reflectedLength(el.maxLength),
    };
  }

  function formIndex(el) {
    if (!el.form) {
      return null;
    }
    const index = formIndexes.get(el.form);
    return index === undefined ? null : index;
  }

  function optionDisabled(opt) {
    return elementMatches(opt, ":disabled") || flagAriaDisabled.get(opt) === true;
  }

  function submitBinding(el) {
    const tag = el.tagName;
    const type = (el.getAttribute("type") || "").toLowerCase();
    const submit =
      (tag === "BUTTON" && (type === "" || type === "submit")) ||
      (tag === "INPUT" && (type === "submit" || type === "image"));
    if (!submit) {
      return { form_method: null, form_action: null };
    }
    const method = el.formMethod ? String(el.formMethod).toLowerCase() : null;
    // formAction is the resolved URL. A document without a base leaves it blank.
    const action = el.hasAttribute("formaction")
      ? String(el.formAction || el.getAttribute("formaction") || "") || null
      : null;
    return { form_method: method, form_action: action };
  }

  function controlValue(el) {
    if (
      el.tagName === "INPUT" ||
      el.tagName === "TEXTAREA" ||
      el.tagName === "SELECT" ||
      el.tagName === "OPTION"
    ) {
      return el.value;
    }
    return null;
  }

  function checkedState(el) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    const role = (el.getAttribute("role") || "").toLowerCase();
    if (el.tagName === "INPUT" && (type === "checkbox" || type === "radio" || role === "switch")) {
      return el.checked === true;
    }
    return null;
  }

  function indexDocument() {
    idCounts = new Map();
    nameCounts = new Map();
    labelsByFor = new Map();
    nthOfType = new Map();
    legendText = new Map();
    formIndexes = new Map();
    flagHidden = new Map();
    flagAriaHidden = new Map();
    flagInert = new Map();
    flagAriaDisabled = new Map();
    styleHidden = new Map();
    displayNone = new Map();
    for (const node of document.querySelectorAll("[id]")) {
      const id = elementId(node);
      if (!id) {
        continue;
      }
      idCounts.set(id, (idCounts.get(id) || 0) + 1);
    }
    for (const node of document.querySelectorAll("[name]")) {
      const name = node.getAttribute("name");
      if (!name || !/^[A-Za-z0-9_-]+$/.test(name)) {
        continue;
      }
      const key = `${node.tagName.toLowerCase()}\n${name}`;
      nameCounts.set(key, (nameCounts.get(key) || 0) + 1);
    }
    for (const label of document.querySelectorAll("label[for]")) {
      const id = label.getAttribute("for");
      if (id && !labelsByFor.has(id)) {
        labelsByFor.set(id, label);
      }
    }
    const forms = document.forms;
    for (let index = 0; index < forms.length; index += 1) {
      formIndexes.set(forms[index], index);
    }
    if (document.documentElement) {
      walkTree(document.documentElement, {
        hidden: false,
        ariaHidden: false,
        inert: false,
        ariaDisabled: false,
        visuallyHidden: false,
      });
    }
  }

  function walkTree(el, inherited) {
    const hidden = inherited.hidden || el.hasAttribute("hidden");
    const ariaHidden = inherited.ariaHidden || el.getAttribute("aria-hidden") === "true";
    const inert = inherited.inert || el.inert === true || el.hasAttribute("inert");
    const ariaDisabled = inherited.ariaDisabled || el.getAttribute("aria-disabled") === "true";
    const style = getComputedStyle(el);
    const visuallyHidden =
      inherited.visuallyHidden || style.display === "none" || style.visibility === "hidden";
    flagHidden.set(el, hidden);
    flagAriaHidden.set(el, ariaHidden);
    flagInert.set(el, inert);
    flagAriaDisabled.set(el, ariaDisabled);
    styleHidden.set(el, visuallyHidden);
    displayNone.set(el, style.display === "none");
    if (el.tagName === "FIELDSET") {
      let text = "";
      for (const child of el.children) {
        if (child.tagName === "LEGEND") {
          text = ownText(child);
          break;
        }
      }
      legendText.set(el, text);
    }
    const counts = new Map();
    const next = { hidden, ariaHidden, inert, ariaDisabled, visuallyHidden };
    for (const child of el.children) {
      const seen = (counts.get(child.tagName) || 0) + 1;
      counts.set(child.tagName, seen);
      nthOfType.set(child, seen);
      walkTree(child, next);
    }
  }

  indexDocument();
  const nodes = [];
  const fields = [
    "tag",
    "role",
    "name",
    "html_id",
    "field_name",
    "input_type",
    "href",
    "form_index",
    "form_method",
    "form_action",
    "disabled",
    "readonly",
    "aria_disabled",
    "inert",
    "hidden",
    "aria_hidden",
    "value",
    "checked",
    "selected",
    "options",
    "aria_expanded",
    "aria_selected",
    "aria_checked",
    "aria_pressed",
    "aria_current",
    "aria_valuemin",
    "aria_valuemax",
    "aria_valuenow",
    "aria_haspopup",
    "aria_controls",
    "box",
    "visible",
    "covered",
    "in_viewport",
    "validation_message",
    "landmark",
    "css",
    "skeleton_path",
    "label_text",
    "group_key",
    "constraints",
  ];
  const elements = Array.from(document.querySelectorAll(SELECTOR)).map((el) => {
    nodes.push(el);
    const rect = el.getBoundingClientRect();
    const visible = isVisible(el, rect);
    const role = elementRole(el);
    const binding = submitBinding(el);
    return [
      el.tagName.toLowerCase(),
      role,
      fallbackName(el),
      elementId(el) || null,
      el.getAttribute("name"),
      el.tagName === "INPUT" ? (el.getAttribute("type") || "text").toLowerCase() : null,
      el.tagName === "A" && el.hasAttribute("href") ? el.href : null,
      formIndex(el),
      binding.form_method,
      binding.form_action,
      role === "option" ? optionDisabled(el) : elementMatches(el, ":disabled"),
      el.readOnly === true,
      flagAriaDisabled.get(el) === true,
      flagInert.get(el) === true,
      flagHidden.get(el) === true,
      flagAriaHidden.get(el) === true,
      controlValue(el),
      checkedState(el),
      el.tagName === "OPTION" ? el.selected === true : null,
      optionsOf(el),
      expanded(el),
      el.getAttribute("aria-selected"),
      el.getAttribute("aria-checked"),
      el.getAttribute("aria-pressed"),
      el.getAttribute("aria-current"),
      el.getAttribute("aria-valuemin"),
      el.getAttribute("aria-valuemax"),
      el.getAttribute("aria-valuenow"),
      el.getAttribute("aria-haspopup"),
      el.getAttribute("aria-controls"),
      { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      visible,
      isCovered(el, rect, visible),
      inViewport(rect),
      el.willValidate ? el.validationMessage : "",
      landmarkOf(el),
      cssOf(el),
      skeletonOf(el),
      labelText(el),
      groupKey(el),
      constraintsOf(el),
    ];
  });

  const forms = Array.from(document.forms).map((form, index) => ({
    index,
    method: (form.getAttribute("method") || "get").toLowerCase(),
    action: readFormAction.call(form),
    // :invalid does not fire invalid listeners. form.checkValidity is skipped
    // because a control named checkValidity replaces the method.
    valid: !elementMatches(form, ":invalid"),
    html_id: elementId(form) || null,
  }));

  const modals = [];
  const seen = new Set();
  function pushModal(el, role) {
    if (seen.has(el) || !isVisible(el, el.getBoundingClientRect())) {
      return;
    }
    seen.add(el);
    modals.push({
      html_id: elementId(el) || null,
      role,
      name: accName(el),
      open: true,
    });
  }
  for (const dialog of document.querySelectorAll("dialog[open]")) {
    if (elementMatches(dialog, ":modal")) {
      pushModal(dialog, "dialog");
    }
  }
  for (const dialog of document.querySelectorAll(
    "[role='dialog'][aria-modal='true'], [role='alertdialog'][aria-modal='true']",
  )) {
    pushModal(dialog, clean(dialog.getAttribute("role")).split(" ")[0] || "dialog");
  }

  return { fields, elements, forms, modals, nodes };
})()
