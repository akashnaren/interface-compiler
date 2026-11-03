// In-page facts for one document. facts.py evaluates this file and reads the
// returned JSON. Elements are rows aligned with `fields` so a large page does
// not repeat every key. Accessibility roles are overlaid in Python; the roles
// recorded here are the HTML ones, which the skeleton path must keep (a summary
// stays button even when Chromium later reports DisclosureTriangle).
(() => {
  // Captured before any later task can pushState or swap the body. The walk
  // itself is synchronous, so these stay the document the rows describe.
  const pageUrl = location.href;
  const pageTitle = document.title;
  const walkStarted = performance.now();
  let truncated = false;

  // Reading every node back is the slow step after the walk. The cap scales
  // with the time left so a short deadline returns a partial row instead of
  // being killed while those nodes are copied out.
  const elementCap =
    typeof WALK_BUDGET_MS === "number" ? Math.max(1, Math.floor(WALK_BUDGET_MS * 3)) : Infinity;

  function budgetSpent() {
    if (truncated) {
      return true;
    }
    if (typeof WALK_BUDGET_MS !== "number") {
      return false;
    }
    if (performance.now() - walkStarted > WALK_BUDGET_MS) {
      truncated = true;
      return true;
    }
    return false;
  }

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

  // Form controls are exposed as named properties and hide these on the form.
  const readId = Object.getOwnPropertyDescriptor(Element.prototype, "id").get;
  const readTagName = Object.getOwnPropertyDescriptor(Element.prototype, "tagName").get;
  const readLocalName = Object.getOwnPropertyDescriptor(Element.prototype, "localName").get;
  const readChildren = Object.getOwnPropertyDescriptor(Element.prototype, "children").get;
  const readParentElement = Object.getOwnPropertyDescriptor(Node.prototype, "parentElement").get;
  const readChildNodes = Object.getOwnPropertyDescriptor(Node.prototype, "childNodes").get;
  const readNodeType = Object.getOwnPropertyDescriptor(Node.prototype, "nodeType").get;
  const readTextContent = Object.getOwnPropertyDescriptor(Node.prototype, "textContent").get;
  const readFormAction = Object.getOwnPropertyDescriptor(HTMLFormElement.prototype, "action").get;
  const readGetAttribute = Element.prototype.getAttribute;
  const readHasAttribute = Element.prototype.hasAttribute;
  const readClosest = Element.prototype.closest;
  const readMatches = Element.prototype.matches;
  const readContains = Node.prototype.contains;
  const readRect = Element.prototype.getBoundingClientRect;
  const readQuery = Element.prototype.querySelector;
  const readQueryAll = Element.prototype.querySelectorAll;
  const readElementFromPoint = Document.prototype.elementFromPoint;
  // A control named willValidate hides the IDL getter on its form. Each
  // element type has its own getter; calling the wrong one throws.
  const readWillValidate = {
    INPUT: Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "willValidate").get,
    BUTTON: Object.getOwnPropertyDescriptor(HTMLButtonElement.prototype, "willValidate").get,
    SELECT: Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "willValidate").get,
    TEXTAREA: Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "willValidate").get,
  };

  function elementId(el) {
    return readId.call(el) || "";
  }

  function tagName(el) {
    return readTagName.call(el);
  }

  function localName(el) {
    return readLocalName.call(el);
  }

  function children(el) {
    return readChildren.call(el);
  }

  function parentElement(el) {
    return readParentElement.call(el);
  }

  function childNodes(el) {
    return readChildNodes.call(el);
  }

  function nodeType(node) {
    return readNodeType.call(node);
  }

  function textContent(node) {
    return readTextContent.call(node);
  }

  function getAttribute(el, name) {
    return readGetAttribute.call(el, name);
  }

  function hasAttribute(el, name) {
    return readHasAttribute.call(el, name);
  }

  function closest(el, selector) {
    return readClosest.call(el, selector);
  }

  function elementMatches(el, selector) {
    return readMatches.call(el, selector);
  }

  function contains(el, node) {
    return readContains.call(el, node);
  }

  function boundingRect(el) {
    return readRect.call(el);
  }

  function query(el, selector) {
    return readQuery.call(el, selector);
  }

  function queryAll(el, selector) {
    return readQueryAll.call(el, selector);
  }

  function elementFromPoint(x, y) {
    return readElementFromPoint.call(document, x, y);
  }

  function willValidate(el) {
    const read = readWillValidate[tagName(el)];
    if (!read) {
      return false;
    }
    return read.call(el) === true;
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  // display:none, hidden, and aria-hidden drop the subtree. visibility:hidden
  // drops only that element's own text; a visibility:visible descendant stays.
  function hidesSubtree(el) {
    if (flagHidden.get(el) === true || flagAriaHidden.get(el) === true) {
      return true;
    }
    if (hasAttribute(el, "hidden") || getAttribute(el, "aria-hidden") === "true") {
      return true;
    }
    if (displayNone.get(el) === true) {
      return true;
    }
    if (displayNone.get(el) === undefined && getComputedStyle(el).display === "none") {
      return true;
    }
    return false;
  }

  function skipsOwnText(el) {
    const hidden = visibilityHidden.get(el);
    if (hidden !== undefined) {
      return hidden === true;
    }
    return getComputedStyle(el).visibility === "hidden";
  }

  function ownText(el) {
    // The element's own text is its name even when this element is hidden.
    // hidesSubtree prunes descendants only; visibility:hidden still skips
    // direct text below and keeps a visibility:visible descendant.
    let text = "";
    const skipDirect = skipsOwnText(el);
    for (const node of childNodes(el)) {
      if (nodeType(node) === Node.TEXT_NODE) {
        if (!skipDirect) {
          text += ` ${textContent(node)}`;
        }
      } else if (nodeType(node) === Node.ELEMENT_NODE) {
        const tag = tagName(node);
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON") {
          continue;
        }
        if (hidesSubtree(node)) {
          continue;
        }
        if (tag === "IMG") {
          text += ` ${getAttribute(node, "alt") || ""}`;
          continue;
        }
        text += ` ${ownText(node)}`;
      }
    }
    return clean(text);
  }

  function accName(el) {
    const labelled = clean(getAttribute(el, "aria-label"));
    if (labelled) {
      return labelled;
    }
    const labelledBy = getAttribute(el, "aria-labelledby");
    if (labelledBy) {
      const parts = [];
      for (const id of labelledBy.split(/\s+/)) {
        if (!id) {
          continue;
        }
        const target = document.getElementById(id);
        if (target) {
          parts.push(ownText(target) || clean(textContent(target)));
        }
      }
      const joined = clean(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    return clean(getAttribute(el, "title"));
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
  let visibilityHidden = new Map();

  function labelFor(el) {
    const id = elementId(el);
    if (!id) {
      return null;
    }
    return labelsByFor.get(id) || null;
  }

  function associatedLabel(el) {
    const explicit = labelFor(el);
    if (explicit) {
      const text = ownText(explicit);
      if (text) {
        return text;
      }
    }
    const wrapping = closest(el, "label");
    if (wrapping && wrapping !== el) {
      const text = ownText(wrapping);
      if (text) {
        return text;
      }
    }
    return "";
  }

  function labelText(el) {
    const fromLabel = associatedLabel(el);
    if (fromLabel) {
      return fromLabel;
    }
    const labelledBy = getAttribute(el, "aria-labelledby");
    if (labelledBy) {
      const parts = [];
      for (const id of labelledBy.split(/\s+/)) {
        const target = id ? document.getElementById(id) : null;
        if (target) {
          parts.push(ownText(target) || clean(textContent(target)));
        }
      }
      const joined = clean(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    const placeholder = clean(getAttribute(el, "placeholder"));
    if (placeholder) {
      return placeholder;
    }
    // A submit value is its name. The fieldset legend must not replace it.
    if (tagName(el) === "INPUT") {
      const type = (getAttribute(el, "type") || "").toLowerCase();
      if (type === "submit" || type === "reset" || type === "button") {
        const value = clean(el.value);
        if (value) {
          return value;
        }
      }
      if (type === "image") {
        const alt = clean(getAttribute(el, "alt"));
        if (alt) {
          return alt;
        }
      }
    }
    const fieldset = closest(el, "fieldset");
    if (fieldset) {
      const text = legendText.get(fieldset) || "";
      if (text) {
        return text;
      }
    }
    return "";
  }

  function elementRole(el) {
    const explicit = clean(getAttribute(el, "role")).split(" ")[0];
    if (explicit) {
      return explicit;
    }
    const tag = localName(el);
    if (tag === "a" && hasAttribute(el, "href")) {
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
      const type = (getAttribute(el, "type") || "text").toLowerCase();
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
    const explicit = clean(getAttribute(el, "role")).split(" ")[0];
    const tag = tagName(el);
    if ((tag === "HEADER" || tag === "FOOTER") && !explicit && parentElement(el) !== document.body) {
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
    let node = parentElement(el);
    while (node && node !== document.documentElement) {
      const role = landmarkRole(node);
      if (role) {
        const name = accName(node);
        return name ? `${role} ${name}` : role;
      }
      node = parentElement(node);
    }
    return "";
  }

  function labelledByText(el) {
    const labelledBy = getAttribute(el, "aria-labelledby");
    if (!labelledBy) {
      return "";
    }
    const parts = [];
    for (const id of String(labelledBy).split(/\s+/)) {
      if (!id) {
        continue;
      }
      const target = document.getElementById(id);
      if (target) {
        parts.push(ownText(target) || clean(textContent(target)));
      }
    }
    return clean(parts.join(" "));
  }

  // Label text beats the value and the default Submit label. Title is last,
  // except an image uses title when alt is empty and Submit only when both are.
  function controlName(el) {
    if (localName(el) !== "input") {
      return null;
    }
    const type = (getAttribute(el, "type") || "").toLowerCase();
    if (
      type !== "submit" &&
      type !== "reset" &&
      type !== "button" &&
      type !== "image" &&
      type !== "file"
    ) {
      return null;
    }
    const by = labelledByText(el);
    if (by) {
      return by;
    }
    const aria = clean(getAttribute(el, "aria-label"));
    if (aria) {
      return aria;
    }
    const label = associatedLabel(el);
    if (label) {
      return label;
    }
    if (type === "file") {
      return "Choose File";
    }
    if (type === "image") {
      const alt = clean(getAttribute(el, "alt"));
      if (alt) {
        return alt;
      }
      const title = clean(getAttribute(el, "title"));
      if (title) {
        return title;
      }
      return "Submit";
    }
    const value = clean(el.value);
    if (value) {
      return value;
    }
    if (type === "submit") {
      return "Submit";
    }
    if (type === "reset") {
      return "Reset";
    }
    return clean(getAttribute(el, "title"));
  }

  function buttonName(el) {
    const by = labelledByText(el);
    if (by) {
      return by;
    }
    const aria = clean(getAttribute(el, "aria-label"));
    if (aria) {
      return aria;
    }
    const text = ownText(el);
    if (text) {
      return text;
    }
    const label = associatedLabel(el);
    if (label) {
      return label;
    }
    return clean(getAttribute(el, "title"));
  }

  function fallbackName(el) {
    const control = controlName(el);
    if (control !== null) {
      return control;
    }
    // Chromium leaves an unlabelled form unnamed. Child text is not its name.
    if (tagName(el) === "FORM") {
      return accName(el);
    }
    if (tagName(el) === "BUTTON") {
      return buttonName(el);
    }
    const named = accName(el);
    if (named) {
      return named;
    }
    const tag = tagName(el);
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      return labelText(el);
    }
    return ownText(el) || labelText(el);
  }

  function groupKey(el) {
    const type = (getAttribute(el, "type") || "").toLowerCase();
    if (tagName(el) === "INPUT" && type === "radio") {
      const name = getAttribute(el, "name");
      if (name) {
        return name;
      }
    }
    const radioGroup = closest(el, "[role='radiogroup']");
    if (radioGroup) {
      const name = accName(radioGroup) || elementId(radioGroup);
      if (name) {
        return name;
      }
    }
    const fieldset = closest(el, "fieldset");
    if (fieldset) {
      const text = legendText.get(fieldset) || "";
      if (text) {
        return text;
      }
    }
    if (hasAttribute(el, "aria-pressed")) {
      const toolbar = closest(el, "[role='toolbar']");
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
    const name = getAttribute(el, "name");
    if (name && /^[A-Za-z0-9_-]+$/.test(name)) {
      const key = `${localName(el)}\n${name}`;
      if (nameCounts.get(key) === 1) {
        return `${localName(el)}[name="${name}"]`;
      }
    }
    const parts = [];
    let node = el;
    while (node && nodeType(node) === 1 && tagName(node) !== "HTML") {
      if (tagName(node) === "BODY") {
        parts.unshift("body");
        break;
      }
      const nth = nthOfType.get(node) || 1;
      parts.unshift(`${localName(node)}:nth-of-type(${nth})`);
      node = parentElement(node);
    }
    return parts.join(" > ");
  }

  function skeletonOf(el) {
    const chain = [];
    let node = el;
    while (node && nodeType(node) === 1 && node !== document.body && node !== document.documentElement) {
      chain.unshift(node);
      node = parentElement(node);
    }
    const parts = [];
    if (document.body) {
      parts.push(`body|${elementRole(document.body)}`);
    }
    for (const item of chain) {
      parts.push(`${localName(item)}|${elementRole(item)}`);
    }
    return parts.join(" > ");
  }

  function expanded(el) {
    const value = getAttribute(el, "aria-expanded");
    if (value !== null) {
      return value;
    }
    if (tagName(el) === "DETAILS") {
      return el.open ? "true" : "false";
    }
    if (tagName(el) === "SUMMARY" && parentElement(el) && tagName(parentElement(el)) === "DETAILS") {
      return parentElement(el).open ? "true" : "false";
    }
    return null;
  }

  function optionsOf(el) {
    if (tagName(el) === "SELECT") {
      return Array.from(el.options, (opt) => ({
        value: opt.value,
        label: clean(opt.label),
        disabled: optionDisabled(opt),
      }));
    }
    let box = getAttribute(el, "role") === "listbox" ? el : null;
    if (!box) {
      const controls = getAttribute(el, "aria-controls");
      const id = controls ? controls.split(/\s+/).find(Boolean) : "";
      const target = id ? document.getElementById(id) : null;
      if (target && (getAttribute(target, "role") === "listbox" || query(target, "[role='option']"))) {
        box = target;
      }
    }
    if (!box) {
      return [];
    }
    return Array.from(queryAll(box, "[role='option']"), (opt) => ({
      value: getAttribute(opt, "data-value") || ownText(opt),
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

  // A same-line miss must not be reused: a mask can cover one sibling only.
  // Hit-testing every inline link is quadratic on a long line, so the point is
  // tested only when a positioned box or a modal backdrop can actually cover it.
  let positioned = [];
  let coverBoxes = null;
  let modalDialog = undefined;

  function coveredBy(el, hit) {
    if (!hit) {
      return true;
    }
    return hit !== el && !contains(el, hit);
  }

  function centerInRect(box, cx, cy) {
    return Boolean(
      box && cx >= box.left && cx < box.right && cy >= box.top && cy < box.bottom,
    );
  }

  function topModal() {
    if (modalDialog !== undefined) {
      return modalDialog;
    }
    modalDialog = null;
    for (const dialog of document.querySelectorAll("dialog[open]")) {
      if (elementMatches(dialog, ":modal")) {
        modalDialog = dialog;
      }
    }
    return modalDialog;
  }

  function boxesThatCover() {
    if (coverBoxes) {
      return coverBoxes;
    }
    coverBoxes = [];
    for (const mask of positioned) {
      coverBoxes.push({ mask, rect: boundingRect(mask) });
    }
    return coverBoxes;
  }

  function isCovered(el, rect, visible) {
    if (!visible) {
      return false;
    }
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (cx < 0 || cy < 0 || cx >= window.innerWidth || cy >= window.innerHeight) {
      return false;
    }
    const modal = topModal();
    if (modal && el !== modal && !contains(modal, el)) {
      return true;
    }
    for (const item of boxesThatCover()) {
      const mask = item.mask;
      if (mask === el || contains(el, mask) || contains(mask, el)) {
        continue;
      }
      if (!centerInRect(item.rect, cx, cy)) {
        continue;
      }
      return coveredBy(el, elementFromPoint(cx, cy));
    }
    return false;
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
      pattern: getAttribute(el, "pattern"),
      min: getAttribute(el, "min"),
      max: getAttribute(el, "max"),
      step: getAttribute(el, "step"),
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
    const tag = tagName(el);
    const type = (getAttribute(el, "type") || "").toLowerCase();
    const submit =
      (tag === "BUTTON" && (type === "" || type === "submit")) ||
      (tag === "INPUT" && (type === "submit" || type === "image"));
    if (!submit) {
      return { form_method: null, form_action: null };
    }
    const method = el.formMethod ? String(el.formMethod).toLowerCase() : null;
    // formAction is the resolved URL. A document without a base leaves it blank.
    const action = hasAttribute(el, "formaction")
      ? String(el.formAction || getAttribute(el, "formaction") || "") || null
      : null;
    return { form_method: method, form_action: action };
  }

  function controlValue(el) {
    if (
      tagName(el) === "INPUT" ||
      tagName(el) === "TEXTAREA" ||
      tagName(el) === "SELECT" ||
      tagName(el) === "OPTION"
    ) {
      return el.value;
    }
    return null;
  }

  function checkedState(el) {
    const type = (getAttribute(el, "type") || "").toLowerCase();
    const role = (getAttribute(el, "role") || "").toLowerCase();
    if (tagName(el) === "INPUT" && (type === "checkbox" || type === "radio" || role === "switch")) {
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
    visibilityHidden = new Map();
    for (const node of document.querySelectorAll("[id]")) {
      const id = elementId(node);
      if (!id) {
        continue;
      }
      idCounts.set(id, (idCounts.get(id) || 0) + 1);
    }
    for (const node of document.querySelectorAll("[name]")) {
      const name = getAttribute(node, "name");
      if (!name || !/^[A-Za-z0-9_-]+$/.test(name)) {
        continue;
      }
      const key = `${localName(node)}\n${name}`;
      nameCounts.set(key, (nameCounts.get(key) || 0) + 1);
    }
    for (const label of document.querySelectorAll("label[for]")) {
      const id = getAttribute(label, "for");
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
        displayHidden: false,
      });
    }
  }

  function walkTree(el, inherited) {
    if (budgetSpent()) {
      return;
    }
    const hidden = inherited.hidden || hasAttribute(el, "hidden");
    const ariaHidden = inherited.ariaHidden || getAttribute(el, "aria-hidden") === "true";
    const inert = inherited.inert || el.inert === true || hasAttribute(el, "inert");
    const ariaDisabled = inherited.ariaDisabled || getAttribute(el, "aria-disabled") === "true";
    const style = getComputedStyle(el);
    const displayHidden = inherited.displayHidden || style.display === "none";
    const visibilityIsHidden = style.visibility === "hidden";
    const visuallyHidden = displayHidden || visibilityIsHidden;
    flagHidden.set(el, hidden);
    flagAriaHidden.set(el, ariaHidden);
    flagInert.set(el, inert);
    flagAriaDisabled.set(el, ariaDisabled);
    styleHidden.set(el, visuallyHidden);
    displayNone.set(el, displayHidden);
    visibilityHidden.set(el, visibilityIsHidden);
    if (style.position !== "static") {
      positioned.push(el);
    }
    if (tagName(el) === "FIELDSET") {
      let text = "";
      for (const child of children(el)) {
        if (tagName(child) === "LEGEND") {
          text = ownText(child);
          break;
        }
      }
      legendText.set(el, text);
    }
    const counts = new Map();
    const next = { hidden, ariaHidden, inert, ariaDisabled, visuallyHidden, displayHidden };
    for (const child of children(el)) {
      if (budgetSpent()) {
        return;
      }
      const seen = (counts.get(tagName(child)) || 0) + 1;
      counts.set(tagName(child), seen);
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
  const elements = [];
  const matched = document.querySelectorAll(SELECTOR);
  for (let index = 0; index < matched.length; index += 1) {
    if (elements.length >= elementCap) {
      truncated = true;
      break;
    }
    if (budgetSpent()) {
      break;
    }
    const el = matched[index];
    nodes.push(el);
    const rect = boundingRect(el);
    const visible = isVisible(el, rect);
    const role = elementRole(el);
    const binding = submitBinding(el);
    elements.push([
      localName(el),
      role,
      fallbackName(el),
      elementId(el) || null,
      getAttribute(el, "name"),
      tagName(el) === "INPUT" ? (getAttribute(el, "type") || "text").toLowerCase() : null,
      tagName(el) === "A" && hasAttribute(el, "href") ? el.href : null,
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
      tagName(el) === "OPTION" ? el.selected === true : null,
      optionsOf(el),
      expanded(el),
      getAttribute(el, "aria-selected"),
      getAttribute(el, "aria-checked"),
      getAttribute(el, "aria-pressed"),
      getAttribute(el, "aria-current"),
      getAttribute(el, "aria-valuemin"),
      getAttribute(el, "aria-valuemax"),
      getAttribute(el, "aria-valuenow"),
      getAttribute(el, "aria-haspopup"),
      getAttribute(el, "aria-controls"),
      { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      visible,
      isCovered(el, rect, visible),
      inViewport(rect),
      willValidate(el) ? el.validationMessage : "",
      landmarkOf(el),
      cssOf(el),
      skeletonOf(el),
      labelText(el),
      groupKey(el),
      constraintsOf(el),
    ]);
  }

  const forms = Array.from(document.forms).map((form, index) => ({
    index,
    method: (getAttribute(form, "method") || "get").toLowerCase(),
    action: readFormAction.call(form),
    // :invalid does not fire invalid listeners. form.checkValidity is skipped
    // because a control named checkValidity replaces the method.
    valid: !elementMatches(form, ":invalid"),
    html_id: elementId(form) || null,
  }));

  const modals = [];
  const seen = new Set();
  function pushModal(el, role) {
    if (seen.has(el) || !isVisible(el, boundingRect(el))) {
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
    pushModal(dialog, clean(getAttribute(dialog, "role")).split(" ")[0] || "dialog");
  }

  return {
    fields,
    elements,
    forms,
    modals,
    nodes,
    url: pageUrl,
    title: pageTitle,
    truncated,
  };
})()
