// In-page facts for one document. facts.py evaluates this file and reads the
// returned JSON. Accessibility roles are overlaid in Python; the roles recorded
// here are the HTML ones, which the skeleton path must keep (a summary stays
// button even when Chromium later reports DisclosureTriangle).
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

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
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

  // Filled once per collection. labelFor and cssOf must not rescan the document.
  let labelsByFor = new Map();
  let idCounts = new Map();
  let nameCounts = new Map();

  function labelFor(el) {
    if (!el.id) {
      return null;
    }
    return labelsByFor.get(el.id) || null;
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
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      const text = legend ? ownText(legend) : "";
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
      if (type === "button" || type === "submit" || type === "reset") {
        return "button";
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
      const name = accName(radioGroup) || radioGroup.id;
      if (name) {
        return name;
      }
    }
    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      const text = legend ? ownText(legend) : "";
      if (text) {
        return text;
      }
    }
    if (el.hasAttribute("aria-pressed")) {
      const toolbar = el.closest("[role='toolbar']");
      if (toolbar) {
        return accName(toolbar) || toolbar.id || null;
      }
    }
    return null;
  }

  function cssOf(el) {
    if (el.id && idCounts.get(el.id) === 1) {
      return `#${CSS.escape(el.id)}`;
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
      const parent = node.parentElement;
      if (!parent) {
        break;
      }
      let nth = 0;
      let count = 0;
      for (const child of parent.children) {
        if (child.tagName === node.tagName) {
          count += 1;
          if (child === node) {
            nth = count;
          }
        }
      }
      parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${nth})`);
      node = parent;
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
        disabled: opt.matches(":disabled"),
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
      disabled: opt.matches(":disabled"),
    }));
  }

  function isVisible(el, rect) {
    if (el.closest("[hidden]")) {
      return false;
    }
    let node = el;
    while (node && node.nodeType === 1) {
      const style = getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden") {
        return false;
      }
      node = node.parentElement;
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

  // HTML non-negative integer: ASCII digits only. "1.5" and "-1" are absent.
  function nonNegativeInteger(value) {
    if (value === null || !/^\d+$/.test(value)) {
      return null;
    }
    return Number(value);
  }

  function constraintsOf(el) {
    return {
      required: el.required === true,
      pattern: el.getAttribute("pattern"),
      min: el.getAttribute("min"),
      max: el.getAttribute("max"),
      step: el.getAttribute("step"),
      minlength: nonNegativeInteger(el.getAttribute("minlength")),
      maxlength: nonNegativeInteger(el.getAttribute("maxlength")),
    };
  }

  function formIndex(el) {
    if (!el.form) {
      return null;
    }
    const index = Array.from(document.forms).indexOf(el.form);
    return index >= 0 ? index : null;
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

  function markerName() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    let hex = "";
    for (const byte of bytes) {
      hex += byte.toString(16).padStart(2, "0");
    }
    return `data-ic-${hex}`;
  }

  function stripMarkers(attribute) {
    for (const el of document.querySelectorAll("[data-ic-fact]")) {
      el.removeAttribute("data-ic-fact");
    }
    for (const el of document.querySelectorAll(`[${CSS.escape(attribute)}]`)) {
      el.removeAttribute(attribute);
    }
  }

  function indexDocument() {
    idCounts = new Map();
    nameCounts = new Map();
    labelsByFor = new Map();
    for (const node of document.querySelectorAll("[id]")) {
      if (!node.id) {
        continue;
      }
      idCounts.set(node.id, (idCounts.get(node.id) || 0) + 1);
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
  }

  indexDocument();
  const markerAttribute = markerName();
  stripMarkers(markerAttribute);
  try {
    const elements = Array.from(document.querySelectorAll(SELECTOR)).map((el, index) => {
      const rect = el.getBoundingClientRect();
      const visible = isVisible(el, rect);
      el.setAttribute(markerAttribute, String(index));
      return {
        marker: String(index),
        tag: el.tagName.toLowerCase(),
        role: elementRole(el),
        name: fallbackName(el),
        html_id: el.id || null,
        field_name: el.getAttribute("name"),
        input_type: el.tagName === "INPUT" ? (el.getAttribute("type") || "text").toLowerCase() : null,
        href: el.tagName === "A" && el.hasAttribute("href") ? el.href : null,
        form_index: formIndex(el),
        disabled: el.matches(":disabled"),
        readonly: el.readOnly === true,
        aria_disabled: Boolean(el.closest("[aria-disabled='true']")),
        inert: el.inert === true || Boolean(el.closest("[inert]")),
        hidden: Boolean(el.closest("[hidden]")),
        aria_hidden: Boolean(el.closest("[aria-hidden='true']")),
        value: controlValue(el),
        checked: checkedState(el),
        selected: el.tagName === "OPTION" ? el.selected === true : null,
        options: optionsOf(el),
        aria_expanded: expanded(el),
        aria_selected: el.getAttribute("aria-selected"),
        aria_checked: el.getAttribute("aria-checked"),
        aria_pressed: el.getAttribute("aria-pressed"),
        aria_current: el.getAttribute("aria-current"),
        aria_valuemin: el.getAttribute("aria-valuemin"),
        aria_valuemax: el.getAttribute("aria-valuemax"),
        aria_valuenow: el.getAttribute("aria-valuenow"),
        aria_haspopup: el.getAttribute("aria-haspopup"),
        aria_controls: el.getAttribute("aria-controls"),
        box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        visible,
        covered: isCovered(el, rect, visible),
        in_viewport: inViewport(rect),
        validation_message: el.willValidate ? el.validationMessage : "",
        landmark: landmarkOf(el),
        css: cssOf(el),
        skeleton_path: skeletonOf(el),
        label_text: labelText(el),
        group_key: groupKey(el),
        constraints: constraintsOf(el),
      };
    });

    const forms = Array.from(document.forms).map((form, index) => ({
      index,
      method: (form.getAttribute("method") || "get").toLowerCase(),
      action: form.action,
      valid: form.checkValidity(),
      html_id: form.id || null,
    }));

    const modals = [];
    const seen = new Set();
    function pushModal(el, role) {
      if (seen.has(el) || !isVisible(el, el.getBoundingClientRect())) {
        return;
      }
      seen.add(el);
      modals.push({
        html_id: el.id || null,
        role,
        name: accName(el),
        open: true,
      });
    }
    for (const dialog of document.querySelectorAll("dialog[open]")) {
      if (dialog.matches(":modal")) {
        pushModal(dialog, "dialog");
      }
    }
    for (const dialog of document.querySelectorAll(
      "[role='dialog'][aria-modal='true'], [role='alertdialog'][aria-modal='true']",
    )) {
      pushModal(dialog, clean(dialog.getAttribute("role")).split(" ")[0] || "dialog");
    }

    return { markerAttribute, elements, forms, modals };
  } catch (error) {
    stripMarkers(markerAttribute);
    throw error;
  }
})()
