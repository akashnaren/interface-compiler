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
  let topModalEl = null;
  let indexFinished = false;
  // Selection, the index, and per-row flags stop on shares of the walk budget.
  // A later phase still runs after an earlier one sets truncated, so a slow
  // index cannot reduce emission to a single row.
  let phaseLimitMs = Infinity;

  function overPhase() {
    return performance.now() - walkStarted > phaseLimitMs;
  }

  function shareLimit(fraction) {
    if (typeof WALK_BUDGET_MS !== "number" || WALK_BUDGET_MS <= 0) {
      return Infinity;
    }
    return WALK_BUDGET_MS * fraction;
  }

  function budgetSpent() {
    if (typeof WALK_BUDGET_MS !== "number") {
      return false;
    }
    // No time was given. Stop without claiming the deadline cut a walk.
    if (WALK_BUDGET_MS <= 0) {
      return true;
    }
    if (overPhase() || performance.now() - walkStarted > WALK_BUDGET_MS) {
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
  const readPreviousElementSibling = Object.getOwnPropertyDescriptor(
    Element.prototype,
    "previousElementSibling",
  ).get;
  const readChildNodes = Object.getOwnPropertyDescriptor(Node.prototype, "childNodes").get;
  const readNodeType = Object.getOwnPropertyDescriptor(Node.prototype, "nodeType").get;
  const readTextContent = Object.getOwnPropertyDescriptor(Node.prototype, "textContent").get;
  const readFormAction = Object.getOwnPropertyDescriptor(HTMLFormElement.prototype, "action").get;
  const readFormElements = Object.getOwnPropertyDescriptor(
    HTMLFormElement.prototype,
    "elements",
  ).get;
  const readGetAttribute = Element.prototype.getAttribute;
  const readHasAttribute = Element.prototype.hasAttribute;
  const readClosest = Element.prototype.closest;
  const readMatches = Element.prototype.matches;
  const readContains = Node.prototype.contains;
  const readRect = Element.prototype.getBoundingClientRect;
  const readCheckVisibility = Element.prototype.checkVisibility;
  const readQuery = Element.prototype.querySelector;
  const readQueryAll = Element.prototype.querySelectorAll;
  const readElementFromPoint = Document.prototype.elementFromPoint;
  const readGetRootNode = Node.prototype.getRootNode;
  const readDocGetElementById = Document.prototype.getElementById;
  const readShadowGetElementById = ShadowRoot.prototype.getElementById;
  const readDocQueryAll = Document.prototype.querySelectorAll;
  const readShadowQueryAll = ShadowRoot.prototype.querySelectorAll;

  // Mixin getters (ParentNode.children) are not own properties of ShadowRoot.
  function prototypeCall(object, name) {
    let current = object;
    while (current) {
      const found = Object.getOwnPropertyDescriptor(current, name);
      if (found && typeof found.value === "function") {
        return found.value;
      }
      current = Object.getPrototypeOf(current);
    }
    return null;
  }

  function prototypeGetter(object, name) {
    let current = object;
    while (current) {
      const found = Object.getOwnPropertyDescriptor(current, name);
      if (found && found.get) {
        return found.get;
      }
      current = Object.getPrototypeOf(current);
    }
    return null;
  }

  const readShadowRoot = prototypeGetter(Element.prototype, "shadowRoot");
  const readShadowHost = prototypeGetter(ShadowRoot.prototype, "host");
  const readShadowChildren = prototypeGetter(ShadowRoot.prototype, "children");
  const readShadowFromPoint = prototypeCall(ShadowRoot.prototype, "elementFromPoint");
  // Piercing every node on a huge page costs more than the walk budget.
  // Above this, shadow content is omitted (fail closed) instead of scanned.
  const pierceLimit = 8000;
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

  function previousElementSibling(el) {
    return readPreviousElementSibling.call(el);
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

  // elementFromPoint stops at a shadow host. Open roots are walked to the real
  // target. A closed root throws or is null, and the host stays the hit.
  function hitTarget(x, y) {
    let hit = elementFromPoint(x, y);
    const seen = new Set();
    while (hit && !seen.has(hit)) {
      seen.add(hit);
      const root = openShadow(hit);
      if (!root || !readShadowFromPoint) {
        break;
      }
      let inner = null;
      try {
        inner = readShadowFromPoint.call(root, x, y);
      } catch (error) {
        break;
      }
      if (!inner || inner === hit) {
        break;
      }
      hit = inner;
    }
    return hit;
  }

  function willValidate(el) {
    const read = readWillValidate[tagName(el)];
    if (!read) {
      return false;
    }
    return read.call(el) === true;
  }

  // Closed shadow roots and unreadable roots are null. Callers omit them.
  function openShadow(el) {
    if (!el || nodeType(el) !== 1 || !readShadowRoot) {
      return null;
    }
    try {
      const root = readShadowRoot.call(el);
      if (!root || nodeType(root) !== 11) {
        return null;
      }
      if (root.mode && root.mode !== "open") {
        return null;
      }
      return root;
    } catch (error) {
      return null;
    }
  }

  function shadowHostOf(el) {
    try {
      const root = readGetRootNode.call(el);
      if (!root || nodeType(root) !== 11) {
        return null;
      }
      return readShadowHost.call(root) || null;
    } catch (error) {
      return null;
    }
  }

  function shadowChildren(el) {
    const root = openShadow(el);
    if (!root || !readShadowChildren) {
      return [];
    }
    try {
      return Array.from(readShadowChildren.call(root));
    } catch (error) {
      return [];
    }
  }

  function parentNodeAcross(node) {
    const parent = parentElement(node);
    if (parent) {
      return parent;
    }
    return shadowHostOf(node);
  }

  function elementById(id, hint) {
    if (!id) {
      return null;
    }
    if (hint) {
      try {
        const root = readGetRootNode.call(hint);
        if (root && nodeType(root) === 11) {
          const found = readShadowGetElementById.call(root, id);
          if (found) {
            return found;
          }
        }
      } catch (error) {
        return null;
      }
    }
    try {
      return readDocGetElementById.call(document, id);
    } catch (error) {
      return null;
    }
  }

  function canPierceShadows() {
    return document.getElementsByTagName("*").length <= pierceLimit;
  }

  function lightHasOpenShadow() {
    let nodes;
    try {
      nodes = readDocQueryAll.call(document, "*");
    } catch (error) {
      return true;
    }
    for (let index = 0; index < nodes.length; index += 1) {
      if (openShadow(nodes[index])) {
        return true;
      }
    }
    return false;
  }

  function describedByText(el) {
    const labelled = getAttribute(el, "aria-describedby");
    if (!labelled) {
      return "";
    }
    const parts = [];
    for (const id of String(labelled).split(/\s+/)) {
      if (!id) {
        continue;
      }
      const target = elementById(id, el);
      if (target) {
        parts.push(ownText(target) || clean(textContent(target)));
      }
    }
    return clean(parts.join(" "));
  }

  // Light DOM plus open shadow roots. A closed root or a thrown read is skipped.
  function collectMatching(selector) {
    let nodes;
    try {
      nodes = readDocQueryAll.call(document, selector);
    } catch (error) {
      return [];
    }
    const found = [];
    for (let index = 0; index < nodes.length; index += 1) {
      found.push(nodes[index]);
    }
    if (!canPierceShadows()) {
      // Open-shadow controls are not collected on a huge page. Say so.
      if (lightHasOpenShadow()) {
        truncated = true;
      }
      return found;
    }
    const seen = new Set(found);
    const stack = [];
    let hosts;
    try {
      hosts = readDocQueryAll.call(document, "*");
    } catch (error) {
      return found;
    }
    for (let index = 0; index < hosts.length; index += 1) {
      const shadow = openShadow(hosts[index]);
      if (shadow) {
        stack.push(shadow);
      }
    }
    while (stack.length) {
      const root = stack.pop();
      let inner;
      let innerHosts;
      try {
        inner = readShadowQueryAll.call(root, selector);
        innerHosts = readShadowQueryAll.call(root, "*");
      } catch (error) {
        continue;
      }
      for (let index = 0; index < inner.length; index += 1) {
        const el = inner[index];
        if (!seen.has(el)) {
          seen.add(el);
          found.push(el);
        }
      }
      for (let index = 0; index < innerHosts.length; index += 1) {
        const shadow = openShadow(innerHosts[index]);
        if (shadow) {
          stack.push(shadow);
        }
      }
    }
    return found;
  }

  function closestAcross(el, selector) {
    const found = closest(el, selector);
    if (found) {
      return found;
    }
    let node = el;
    const seen = new Set();
    while (node && !seen.has(node)) {
      seen.add(node);
      const host = shadowHostOf(node);
      if (!host || seen.has(host)) {
        return null;
      }
      if (elementMatches(host, selector)) {
        return host;
      }
      const outer = closest(host, selector);
      if (outer) {
        return outer;
      }
      node = host;
    }
    return null;
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
    // Same parse as ariaHiddenState, on this node only. The walk already recurses.
    const ariaHidden = getAttribute(el, "aria-hidden");
    if (
      hasAttribute(el, "hidden") ||
      (ariaHidden !== null && asciiLower(ariaHidden.trim()) === "true")
    ) {
      return true;
    }
    if (displayNone.get(el) === true) {
      return true;
    }
    if (displayNone.get(el) === false) {
      return false;
    }
    // Closed details content is not display:none, and its text still belongs
    // in the name. checkVisibility is false there, so it cannot decide this.
    return getComputedStyle(el).display === "none" || closest(el, "[hidden]") !== null;
  }

  function skipsOwnText(el) {
    const hidden = visibilityHidden.get(el);
    if (hidden !== undefined) {
      return hidden === true;
    }
    return getComputedStyle(el).visibility === "hidden";
  }

  function ownText(el, nested) {
    // A visibility:hidden element's name stays empty, descendant included.
    // A visible parent still walks through it, so "Go VIS" keeps VIS.
    if (!nested && skipsOwnText(el)) {
      return "";
    }
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
        text += ` ${ownText(node, true)}`;
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
        const target = elementById(id, el);
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
  let indexedForms = [];
  let flagHidden = new Map();
  let flagAriaHidden = new Map();
  let flagInert = new Map();
  let flagAriaDisabled = new Map();
  let styleHidden = new Map();
  let displayNone = new Map();
  let visibilityHidden = new Map();
  // Partial id and name scans count the first duplicate and miss the rest.
  let idsFinished = false;
  let namesFinished = false;

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
        const target = id ? elementById(id, el) : null;
        if (target) {
          parts.push(ownText(target) || clean(textContent(target)));
        }
      }
      const joined = clean(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    const aria = clean(getAttribute(el, "aria-label"));
    if (aria) {
      return aria;
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
    let node = parentNodeAcross(el);
    while (node && node !== document.documentElement) {
      const role = landmarkRole(node);
      if (role) {
        const name = accName(node);
        return name ? `${role} ${name}` : role;
      }
      node = parentNodeAcross(node);
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
      const target = elementById(id, el);
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

  function namedFromContent(el) {
    const role = elementRole(el);
    return (
      role === "link" ||
      role === "button" ||
      role === "menuitem" ||
      role === "tab" ||
      role === "option" ||
      role === "treeitem" ||
      role === "checkbox" ||
      role === "radio" ||
      role === "switch" ||
      role === "menuitemcheckbox" ||
      role === "menuitemradio" ||
      role === "gridcell"
    );
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
    // Chromium names a <button> from its label before the button's text.
    // A link or an ARIA widget keeps its text, and title beats that label.
    if (tagName(el) === "BUTTON") {
      const label = associatedLabel(el);
      if (label) {
        return label;
      }
    }
    const text = ownText(el);
    if (text) {
      return text;
    }
    if (tagName(el) === "INPUT") {
      const type = (getAttribute(el, "type") || "text").toLowerCase();
      if (type === "checkbox" || type === "radio") {
        const label = associatedLabel(el);
        if (label) {
          return label;
        }
      }
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
    if (tagName(el) === "BUTTON" || namedFromContent(el)) {
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

  function idShortcut(el) {
    // #id does not reach into a shadow tree. The positional path does.
    if (!idsFinished || shadowHostOf(el)) {
      return "";
    }
    const id = elementId(el);
    if (id && idCounts.get(id) === 1) {
      return `#${CSS.escape(id)}`;
    }
    return "";
  }

  function nameShortcut(el) {
    if (!namesFinished || shadowHostOf(el)) {
      return "";
    }
    const name = getAttribute(el, "name");
    if (name && /^[A-Za-z0-9_-]+$/.test(name)) {
      const key = `${localName(el)}\n${name}`;
      if (nameCounts.get(key) === 1) {
        return `${localName(el)}[name="${name}"]`;
      }
    }
    return "";
  }

  function cssOf(el) {
    if (!shadowHostOf(el)) {
      const shortcut = idShortcut(el) || nameShortcut(el);
      if (shortcut) {
        return shortcut;
      }
    }
    const segments = [];
    let current = [];
    let node = el;
    const seen = new Set();
    while (node && nodeType(node) === 1 && tagName(node) !== "HTML") {
      if (seen.has(node)) {
        return "";
      }
      seen.add(node);
      if (tagName(node) === "BODY") {
        current.unshift("body");
        break;
      }
      // A missing nth-of-type must not become 1. That selector names an
      // earlier sibling, so the row is omitted instead.
      const nth = nthOfType.get(node);
      if (typeof nth !== "number" || nth < 1) {
        return "";
      }
      current.unshift(`${localName(node)}:nth-of-type(${nth})`);
      const parent = parentElement(node);
      if (parent) {
        node = parent;
        continue;
      }
      const host = shadowHostOf(node);
      if (!host) {
        return "";
      }
      segments.unshift(current.join(" > "));
      current = [];
      node = host;
    }
    if (current.length) {
      segments.unshift(current.join(" > "));
    }
    return segments.join(" >>> ");
  }

  function skeletonOf(el) {
    const chain = [];
    let node = el;
    while (node && nodeType(node) === 1 && node !== document.body && node !== document.documentElement) {
      chain.unshift(node);
      node = parentNodeAcross(node);
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

  function renderedBox(el) {
    if (!el) {
      return false;
    }
    if (hasAttribute(el, "hidden") || closest(el, "[hidden]") !== null) {
      return false;
    }
    let style;
    try {
      style = getComputedStyle(el);
    } catch (error) {
      return false;
    }
    if (style.display === "none" || style.visibility === "hidden") {
      return false;
    }
    const rect = boundingRect(el);
    return rect.width > 0 && rect.height > 0;
  }

  function optionPopup(el) {
    if (tagName(el) === "SELECT" || getAttribute(el, "role") === "listbox") {
      return el;
    }
    const controls = getAttribute(el, "aria-controls");
    const id = controls ? controls.split(/\s+/).find(Boolean) : "";
    const target = id ? elementById(id, el) : null;
    if (target && (getAttribute(target, "role") === "listbox" || query(target, "[role='option']"))) {
      return target;
    }
    return null;
  }

  function popupRendered(el) {
    if (tagName(el) === "SELECT") {
      return true;
    }
    return renderedBox(optionPopup(el));
  }

  function controlType(el) {
    const tag = tagName(el);
    if (tag === "INPUT") {
      return (getAttribute(el, "type") || "text").toLowerCase();
    }
    if (tag === "BUTTON") {
      return (getAttribute(el, "type") || "submit").toLowerCase();
    }
    return null;
  }

  function topmostModal(modals) {
    if (!modals.length) {
      return null;
    }
    // Hit-test each dialog at its visible center. The dialog that contains
    // that hit is painted there. Never sample (1, 1). z-index is the fallback
    // when that test cannot pick a single dialog.
    const hits = [];
    for (let index = 0; index < modals.length; index += 1) {
      const modal = modals[index];
      const point = modalPoint(modal);
      if (!point) {
        continue;
      }
      const target = hitTarget(point.x, point.y);
      if (target && nodeInside(modal, target)) {
        hits.push(modal);
      }
    }
    if (hits.length === 1) {
      return hits[0];
    }
    return highestModal(hits.length ? hits : modals);
  }

  function modalPoint(modal) {
    const center = clippedPoint(boundingRect(modal));
    if (center) {
      return center;
    }
    let control = null;
    try {
      control = query(modal, "button, a[href], input, select, textarea, [role='button']");
    } catch (error) {
      control = null;
    }
    if (!control) {
      return null;
    }
    return clippedPoint(boundingRect(control));
  }

  function nodeInside(modal, node) {
    let current = node;
    const seen = new Set();
    while (current && !seen.has(current)) {
      if (current === modal) {
        return true;
      }
      seen.add(current);
      current = parentNodeAcross(current);
    }
    return false;
  }

  function highestModal(modals) {
    let best = modals[0];
    let bestChain = modalChain(best);
    let bestIndex = 0;
    for (let index = 1; index < modals.length; index += 1) {
      const chain = modalChain(modals[index]);
      if (chainOutranks(chain, index, bestChain, bestIndex)) {
        best = modals[index];
        bestChain = chain;
        bestIndex = index;
      }
    }
    return best;
  }

  // A transformed, filtered, or opacity ancestor traps the dialog's own
  // z-index. Compare those contexts from the root. A top-layer dialog is
  // above the page, and its ancestors do not count.
  function modalChain(modal) {
    let topLayer = false;
    try {
      topLayer = elementMatches(modal, ":modal");
    } catch (error) {
      topLayer = false;
    }
    if (topLayer) {
      return { top: true, contexts: [{ node: modal, z: usedZ(modal) }] };
    }
    const contexts = [];
    let node = modal;
    const seen = new Set();
    let own = true;
    while (node && nodeType(node) === 1 && !seen.has(node)) {
      seen.add(node);
      let style = null;
      try {
        style = getComputedStyle(node);
      } catch (error) {
        break;
      }
      if (own) {
        contexts.push({ node, z: usedZ(modal, style) });
        own = false;
      } else {
        const level = contextLevel(style);
        if (level !== null) {
          contexts.push({ node, z: level });
        }
      }
      node = parentNodeAcross(node);
    }
    contexts.reverse();
    return { top: false, contexts };
  }

  function usedZ(modal, style) {
    let read = style;
    if (!read) {
      try {
        read = getComputedStyle(modal);
      } catch (error) {
        return 0;
      }
    }
    const value = Number(read.zIndex);
    return Number.isFinite(value) ? value : 0;
  }

  function contextLevel(style) {
    const z = Number(style.zIndex);
    const finite = Number.isFinite(z) ? z : 0;
    const positioned =
      style.position === "relative" ||
      style.position === "absolute" ||
      style.position === "fixed" ||
      style.position === "sticky";
    if (positioned && style.zIndex !== "auto") {
      return finite;
    }
    const will = style.willChange || "";
    const traps =
      style.position === "fixed" ||
      style.position === "sticky" ||
      style.opacity !== "1" ||
      (style.transform && style.transform !== "none") ||
      (style.filter && style.filter !== "none") ||
      (style.perspective && style.perspective !== "none") ||
      style.isolation === "isolate" ||
      (style.mixBlendMode && style.mixBlendMode !== "normal") ||
      (style.backdropFilter && style.backdropFilter !== "none") ||
      (style.webkitBackdropFilter && style.webkitBackdropFilter !== "none") ||
      /transform|opacity|filter/.test(will);
    return traps ? finite : null;
  }

  function chainOutranks(chain, index, best, bestIndex) {
    if (chain.top !== best.top) {
      return chain.top;
    }
    const left = chain.contexts;
    const right = best.contexts;
    const length = Math.min(left.length, right.length);
    for (let level = 0; level < length; level += 1) {
      const a = left[level];
      const b = right[level];
      if (a.node === b.node) {
        continue;
      }
      // Different contexts. A nested z-index does not escape its ancestor.
      if (a.z !== b.z) {
        return a.z > b.z;
      }
      return index >= bestIndex;
    }
    if (left.length !== right.length) {
      return left.length > right.length;
    }
    // Later DOM order wins a tie.
    return index >= bestIndex;
  }

  function inTopModal(el) {
    if (!topModalEl) {
      return false;
    }
    let node = el;
    const seen = new Set();
    while (node && !seen.has(node)) {
      if (node === topModalEl) {
        return true;
      }
      seen.add(node);
      node = parentNodeAcross(node);
    }
    return false;
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
      const target = id ? elementById(id, el) : null;
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
    // A row whose flags were not computed is omitted from visibility. Default
    // false would report a covered control as actionable.
    if (!styleHidden.has(el)) {
      return false;
    }
    if (flagHidden.get(el) === true || styleHidden.get(el) === true) {
      return false;
    }
    return rect.width > 0 && rect.height > 0;
  }

  function asciiLower(value) {
    let lower = "";
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      lower += code >= 65 && code <= 90 ? String.fromCharCode(code + 32) : value.charAt(index);
    }
    return lower;
  }

  // Absent or empty keeps walking. ASCII-lowercased "false", with no trim,
  // is enabled. Any other non-empty value is disabled.
  function ariaDisabledState(el) {
    let node = el;
    while (node && nodeType(node) === 1) {
      const value = getAttribute(node, "aria-disabled");
      if (value !== null && value !== "") {
        return asciiLower(value) !== "false";
      }
      node = parentNodeAcross(node);
    }
    return false;
  }

  // A descendant false does not reveal a hidden ancestor. Any value that
  // trims and lowercases to "true" hides this element.
  function ariaHiddenState(el) {
    let node = el;
    while (node && nodeType(node) === 1) {
      const value = getAttribute(node, "aria-hidden");
      if (value !== null && asciiLower(value.trim()) === "true") {
        return true;
      }
      node = parentNodeAcross(node);
    }
    return false;
  }

  // Flags come from this element's ancestors, not from the document walk.
  // One closest() per condition so an inner inert node does not hide an outer
  // hidden ancestor. visibility:hidden still has a box, so it is a second check.
  function applyRowFlags(el) {
    const hidden = closestAcross(el, "[hidden]") !== null;
    const ariaHidden = ariaHiddenState(el);
    const inert = closestAcross(el, "[inert]") !== null;
    const ariaDisabled = ariaDisabledState(el);
    let displayHidden = hidden;
    let visibilityIsHidden = false;
    if (typeof readCheckVisibility === "function") {
      const rendered = readCheckVisibility.call(el) === true;
      if (!rendered) {
        displayHidden = true;
      } else if (readCheckVisibility.call(el, { visibilityProperty: true }) !== true) {
        visibilityIsHidden = true;
      }
    } else {
      const style = getComputedStyle(el);
      displayHidden = style.display === "none" || hidden;
      visibilityIsHidden = style.visibility === "hidden";
    }
    flagHidden.set(el, hidden);
    flagAriaHidden.set(el, ariaHidden);
    flagInert.set(el, inert);
    flagAriaDisabled.set(el, ariaDisabled);
    displayNone.set(el, displayHidden);
    visibilityHidden.set(el, visibilityIsHidden);
    styleHidden.set(el, displayHidden || visibilityIsHidden);
  }

  function coveredBy(el, hit) {
    if (!hit) {
      return true;
    }
    return hit !== el && !contains(el, hit);
  }

  function pastBudget() {
    return (
      typeof WALK_BUDGET_MS === "number" &&
      WALK_BUDGET_MS > 0 &&
      performance.now() - walkStarted > WALK_BUDGET_MS
    );
  }

  // Read-back has to return before the hard deadline. The reserved second
  // covers this copy and the overlay; the tail is the trip back to Python.
  function pastReadback() {
    if (typeof WALK_BUDGET_MS !== "number" || WALK_BUDGET_MS <= 0) {
      return false;
    }
    const reserveMs = typeof WALK_RESERVE_MS === "number" ? WALK_RESERVE_MS : 1000;
    const tailMs = 800;
    return performance.now() - walkStarted > WALK_BUDGET_MS + reserveMs - tailMs;
  }

  function withinBudget() {
    if (pastReadback()) {
      truncated = true;
      return false;
    }
    return !budgetSpent();
  }

  // Sample the center of the rectangle clipped to the viewport. A control
  // whose geometric center is off-screen can still show a covered sliver.
  function clippedPoint(rect) {
    const left = Math.max(rect.left, 0);
    const top = Math.max(rect.top, 0);
    const right = Math.min(rect.right, window.innerWidth);
    const bottom = Math.min(rect.bottom, window.innerHeight);
    if (right <= left || bottom <= top) {
      return null;
    }
    return { x: (left + right) / 2, y: (top + bottom) / 2 };
  }

  // One elementFromPoint walks every inline box, so a long line is quadratic.
  // A call is counted after it returns. Samples the loop does not reach are
  // covered, and the walk is truncated. Nothing here writes the page.
  const hitCapMs = 300;
  const longRunCount = 40;
  const longRunHits = 12;
  const longRunMs = 40;
  const slowHitMs = 80;

  const phrasingSelector = [
    "a",
    "abbr",
    "b",
    "bdi",
    "bdo",
    "br",
    "cite",
    "code",
    "data",
    "dfn",
    "em",
    "i",
    "kbd",
    "mark",
    "q",
    "s",
    "samp",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "time",
    "u",
    "var",
    "wbr",
  ].join(",");

  function phrasingCount() {
    let count = 0;
    try {
      count = document.querySelectorAll(phrasingSelector).length;
    } catch (error) {
      return 12001;
    }
    if (count > 12000 || !canPierceShadows()) {
      return count;
    }
    const stack = [];
    const seen = new Set();
    let hosts;
    try {
      hosts = readDocQueryAll.call(document, "*");
    } catch (error) {
      return count;
    }
    for (let index = 0; index < hosts.length; index += 1) {
      const shadow = openShadow(hosts[index]);
      if (shadow) {
        stack.push(shadow);
      }
    }
    while (stack.length && count <= 12000) {
      const root = stack.pop();
      if (seen.has(root)) {
        continue;
      }
      seen.add(root);
      try {
        count += readShadowQueryAll.call(root, phrasingSelector).length;
        const inner = readShadowQueryAll.call(root, "*");
        for (let index = 0; index < inner.length && count <= 12000; index += 1) {
          const shadow = openShadow(inner[index]);
          if (shadow) {
            stack.push(shadow);
          }
        }
      } catch (error) {
        // Unreadable root: stop counting it. The hit test stays fail-closed.
      }
    }
    return count;
  }

  function hugeHitTarget() {
    // One elementFromPoint walks every inline box. Phrasing runs, including
    // ones inside open shadow roots, skip the call. A 4000-row table stays
    // under both ceilings.
    if (document.getElementsByTagName("*").length > 60000) {
      return true;
    }
    return phrasingCount() > 12000;
  }

  function failClosedHits(flags, points, from) {
    truncated = true;
    for (let index = from; index < points.length; index += 1) {
      flags[points[index].index] = true;
    }
  }

  function coverageOf(els, rects) {
    const flags = [];
    const viewport = [];
    for (let index = 0; index < els.length; index += 1) {
      flags.push(false);
      const rect = rects[index];
      if (!isVisible(els[index], rect)) {
        continue;
      }
      const point = clippedPoint(rect);
      if (!point) {
        continue;
      }
      viewport.push({ index, x: point.x, y: point.y });
    }
    if (hugeHitTarget()) {
      failClosedHits(flags, viewport, 0);
      return flags;
    }
    const normal = [];
    const longRuns = [];
    let run = [];
    function flushRun() {
      if (run.length >= longRunCount) {
        longRuns.push(run);
      } else {
        for (const point of run) {
          normal.push(point);
        }
      }
      run = [];
    }
    for (const point of viewport) {
      if (run.length && Math.abs(point.y - run[0].y) > 2) {
        flushRun();
      }
      run.push(point);
    }
    flushRun();
    const hitStarted = performance.now();
    function sample(list, maxCount, maxMs) {
      let seen = 0;
      const started = performance.now();
      for (; seen < list.length; seen += 1) {
        if (seen >= maxCount) {
          break;
        }
        if (pastBudget() || performance.now() - hitStarted > hitCapMs) {
          break;
        }
        if (performance.now() - started > maxMs) {
          break;
        }
        const used = performance.now() - walkStarted;
        if (
          typeof WALK_BUDGET_MS === "number" &&
          WALK_BUDGET_MS > 0 &&
          WALK_BUDGET_MS - used < 250
        ) {
          break;
        }
        const point = list[seen];
        const callStarted = performance.now();
        flags[point.index] = coveredBy(els[point.index], hitTarget(point.x, point.y));
        if (performance.now() - callStarted > slowHitMs) {
          seen += 1;
          break;
        }
      }
      if (seen < list.length) {
        failClosedHits(flags, list, seen);
      }
    }
    // Short targets first, so a long line cannot fail-close the rest of the page.
    sample(normal, Infinity, hitCapMs);
    for (const line of longRuns) {
      sample(line, longRunHits, longRunMs);
    }
    return flags;
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
      (tag === "BUTTON" && type !== "button" && type !== "reset") ||
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
    if (!withinBudget()) {
      return;
    }
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
    idsFinished = false;
    namesFinished = false;
    const ids = collectMatching("[id]");
    for (let index = 0; index < ids.length; index += 1) {
      if (!withinBudget()) {
        return;
      }
      const id = elementId(ids[index]);
      if (!id) {
        continue;
      }
      idCounts.set(id, (idCounts.get(id) || 0) + 1);
    }
    idsFinished = true;
    const named = collectMatching("[name]");
    for (let index = 0; index < named.length; index += 1) {
      if (!withinBudget()) {
        return;
      }
      const name = getAttribute(named[index], "name");
      if (!name || !/^[A-Za-z0-9_-]+$/.test(name)) {
        continue;
      }
      const key = `${localName(named[index])}\n${name}`;
      nameCounts.set(key, (nameCounts.get(key) || 0) + 1);
    }
    namesFinished = true;
    const labels = collectMatching("label[for]");
    for (let index = 0; index < labels.length; index += 1) {
      if (!withinBudget()) {
        return;
      }
      const id = getAttribute(labels[index], "for");
      if (id && !labelsByFor.has(id)) {
        labelsByFor.set(id, labels[index]);
      }
    }
    const forms = [];
    for (let index = 0; index < document.forms.length; index += 1) {
      forms.push(document.forms[index]);
    }
    if (canPierceShadows()) {
      for (const form of collectMatching("form")) {
        if (!forms.includes(form)) {
          forms.push(form);
        }
      }
    }
    indexedForms = forms;
    for (let index = 0; index < forms.length; index += 1) {
      if (!withinBudget()) {
        return;
      }
      formIndexes.set(forms[index], index);
    }
    indexFinished = document.documentElement ? walkTree(document.documentElement) : true;
  }

  // nth-of-type and legends only. Ancestor flags are computed per chosen row
  // so a walk that stops early does not leave later controls looking actionable.
  // False means the walk stopped, and the accessibility tree is not safe to open.
  function walkTree(el) {
    if (!withinBudget()) {
      return false;
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
    for (const child of children(el)) {
      if (!withinBudget()) {
        return false;
      }
      const seen = (counts.get(tagName(child)) || 0) + 1;
      counts.set(tagName(child), seen);
      nthOfType.set(child, seen);
      if (!walkTree(child)) {
        return false;
      }
    }
    const shadowCounts = new Map();
    for (const child of shadowChildren(el)) {
      if (!withinBudget()) {
        return false;
      }
      const seenCount = (shadowCounts.get(tagName(child)) || 0) + 1;
      shadowCounts.set(tagName(child), seenCount);
      nthOfType.set(child, seenCount);
      if (!walkTree(child)) {
        return false;
      }
    }
    return true;
  }

  // Fill nth-of-type from earlier siblings when the document walk stopped
  // first. A known sibling of the same tag makes the next row constant time,
  // so a long table does not rescan from the start. The scan gives up at
  // read-back and the row is then omitted rather than given nth 1.
  function recordNth(el) {
    if (nthOfType.has(el)) {
      return true;
    }
    const tag = tagName(el);
    let scanned = 0;
    let sib = previousElementSibling(el);
    let known = 0;
    const gap = [];
    while (sib) {
      scanned += 1;
      if ((scanned & 127) === 0 && pastReadback()) {
        return false;
      }
      if (tagName(sib) === tag) {
        const prior = nthOfType.get(sib);
        if (typeof prior === "number" && prior > 0) {
          known = prior;
          break;
        }
        gap.push(sib);
      }
      sib = previousElementSibling(sib);
    }
    let nth = known + 1;
    for (let index = gap.length - 1; index >= 0; index -= 1) {
      nthOfType.set(gap[index], nth);
      nth += 1;
    }
    nthOfType.set(el, nth);
    return true;
  }

  function nthReady(el) {
    let node = el;
    while (node && nodeType(node) === 1 && tagName(node) !== "HTML") {
      if (tagName(node) === "BODY") {
        return true;
      }
      if (!recordNth(node)) {
        return false;
      }
      node = parentNodeAcross(node);
    }
    return true;
  }

  // A finished id or name count can skip nth-of-type. An unfinished count
  // has only seen the first duplicate, so the row keeps the positional path.
  function selectorWithoutNth(el) {
    return idShortcut(el) !== "" || nameShortcut(el) !== "";
  }

  function textAlternatives(el) {
    const parts = [
      clean(textContent(el)),
      clean(getAttribute(el, "value")),
      clean(getAttribute(el, "alt")),
      clean(getAttribute(el, "title")),
      associatedLabel(el),
    ];
    const tag = tagName(el);
    if (tag === "BUTTON" || tag === "A" || tag === "SUMMARY") {
      const images = queryAll(el, "img[alt]");
      for (let index = 0; index < images.length; index += 1) {
        parts.push(clean(getAttribute(images[index], "alt")));
      }
    }
    return parts.filter(Boolean);
  }

  function elementRow(el, rect, coveredFlag) {
    const visible = isVisible(el, rect);
    const role = elementRole(el);
    const binding = submitBinding(el);
    return [
      localName(el),
      role,
      fallbackName(el),
      elementId(el) || null,
      getAttribute(el, "name"),
      controlType(el),
      tagName(el) === "A" && hasAttribute(el, "href") ? el.href : null,
      formIndex(el),
      binding.form_method,
      binding.form_action,
      role === "option"
        ? optionDisabled(el)
        : elementMatches(el, ":disabled") || fieldsetDisables(el),
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
      coveredFlag,
      inViewport(rect),
      willValidate(el) ? el.validationMessage : "",
      landmarkOf(el),
      cssOf(el),
      skeletonOf(el),
      labelText(el),
      groupKey(el),
      constraintsOf(el),
      inTopModal(el),
      popupRendered(el),
      clean(getAttribute(el, "placeholder")),
      clean(getAttribute(el, "title")),
      describedByText(el),
      textAlternatives(el),
    ];
  }

  function deadlinePayload() {
    return {
      meta: JSON.stringify({
        fields: [],
        forms: [],
        modals: [],
        url: pageUrl,
        title: pageTitle,
        truncated: false,
        deadline: true,
        chunks: 0,
        controls: 0,
      }),
      chunks: [],
      nodes: [],
    };
  }

  if (typeof WALK_BUDGET_MS === "number" && WALK_BUDGET_MS <= 0) {
    if (collectMatching(SELECTOR).length > 0) {
      return deadlinePayload();
    }
  }

  // Selection and the index each stop on a share of the walk budget. Flags
  // then take half of the time still left before read-back, and emission
  // keeps the rest, so a throttled table still ships a prefix.
  const matched = collectMatching(SELECTOR);
  phaseLimitMs = shareLimit(0.3);
  const chosen = [];
  const rects = [];
  for (let index = 0; index < matched.length; index += 1) {
    if (budgetSpent()) {
      break;
    }
    chosen.push(matched[index]);
    rects.push(boundingRect(matched[index]));
  }
  if (chosen.length === 0 && matched.length > 0) {
    return deadlinePayload();
  }

  phaseLimitMs = shareLimit(0.45);
  indexDocument();
  const reserveMs = typeof WALK_RESERVE_MS === "number" ? WALK_RESERVE_MS : 1000;
  const readbackAt =
    typeof WALK_BUDGET_MS === "number" && WALK_BUDGET_MS > 0
      ? WALK_BUDGET_MS + reserveMs - 800
      : Infinity;
  const elapsedNow = performance.now() - walkStarted;
  phaseLimitMs = elapsedNow + Math.max(0, (readbackAt - elapsedNow) * 0.5);
  const kept = [];
  const keptRects = [];
  for (let index = 0; index < chosen.length; index += 1) {
    if (overPhase() || pastReadback()) {
      truncated = true;
      break;
    }
    const row = chosen[index];
    // Flags come from this row's ancestors. A positional selector still needs
    // a real nth-of-type; when that cannot be filled in time the row is omitted.
    if (!selectorWithoutNth(row) && !nthReady(row)) {
      truncated = true;
      break;
    }
    try {
      applyRowFlags(row);
    } catch (error) {
      truncated = true;
      break;
    }
    if (!styleHidden.has(row) || !cssOf(row)) {
      truncated = true;
      break;
    }
    kept.push(row);
    keptRects.push(rects[index]);
  }
  phaseLimitMs = Infinity;
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
    "in_dialog",
    "popup_open",
    "placeholder",
    "title",
    "described_by",
    "text_alternatives",
  ];
  const covered = coverageOf(kept, keptRects);
  const keptAt = new Map();
  for (let index = 0; index < kept.length; index += 1) {
    keptAt.set(kept[index], index);
  }
  function isSubmitControl(control) {
    const tag = tagName(control);
    const type = (getAttribute(control, "type") || "").toLowerCase();
    return (
      (tag === "BUTTON" && type !== "button" && type !== "reset") ||
      (tag === "INPUT" && (type === "submit" || type === "image"))
    );
  }

  function isFillable(control) {
    const tag = tagName(control);
    const type = (getAttribute(control, "type") || "").toLowerCase();
    if (tag === "INPUT") {
      return (
        type !== "hidden" &&
        type !== "submit" &&
        type !== "image" &&
        type !== "reset" &&
        type !== "button"
      );
    }
    return tag === "SELECT" || tag === "TEXTAREA";
  }

  function firstLegendChild(fieldset) {
    try {
      for (const child of children(fieldset)) {
        if (tagName(child) === "LEGEND") {
          return child;
        }
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function inFirstLegend(el, fieldset) {
    const legend = firstLegendChild(fieldset);
    if (!legend) {
      return false;
    }
    if (legend === el) {
      return true;
    }
    try {
      return contains(legend, el);
    } catch (error) {
      return false;
    }
  }

  // :disabled is false for the first legend of that fieldset. An outer
  // disabled fieldset still counts. A submit outside does not turn the
  // other controls back on.
  function fieldsetDisables(control) {
    let node = control;
    const seen = new Set();
    while (node) {
      const fieldset = closestAcross(node, "fieldset[disabled]");
      if (!fieldset || seen.has(fieldset)) {
        return false;
      }
      seen.add(fieldset);
      if (!inFirstLegend(control, fieldset)) {
        return true;
      }
      node = parentNodeAcross(fieldset);
    }
    return false;
  }

  function formControls(form) {
    // form.elements includes controls associated with form=, not only descendants.
    const listed = readFormElements.call(form);
    const controls = [];
    for (let index = 0; index < listed.length; index += 1) {
      controls.push(listed[index]);
    }
    return controls;
  }

  function fieldsetDisabled(form) {
    let controls;
    try {
      controls = formControls(form);
    } catch (error) {
      return true;
    }
    // Any fillable control in a disabled fieldset disables the form. An enabled
    // control earlier in the list must not hide that. A first-legend control
    // still keeps the form available.
    let blocked = false;
    let legendAvailable = false;
    for (let index = 0; index < controls.length; index += 1) {
      const control = controls[index];
      if (isSubmitControl(control)) {
        const fieldset = closestAcross(control, "fieldset[disabled]");
        if (fieldset && inFirstLegend(control, fieldset)) {
          legendAvailable = true;
        }
        continue;
      }
      if (!isFillable(control)) {
        continue;
      }
      if (fieldsetDisables(control)) {
        blocked = true;
        continue;
      }
      try {
        const fieldset = closestAcross(control, "fieldset[disabled]");
        if (
          fieldset &&
          inFirstLegend(control, fieldset) &&
          !elementMatches(control, ":disabled")
        ) {
          legendAvailable = true;
        }
      } catch (error) {
        return true;
      }
    }
    if (legendAvailable) {
      return false;
    }
    if (blocked) {
      return true;
    }
    const fieldset = closestAcross(form, "fieldset[disabled]");
    return fieldset !== null && !inFirstLegend(form, fieldset);
  }
  const forms = (indexedForms.length ? indexedForms : Array.from(document.forms)).map(
    (form, index) => {
      const at = keptAt.get(form);
      if (!styleHidden.has(form)) {
        try {
          applyRowFlags(form);
        } catch (error) {
          flagInert.set(form, true);
        }
      }
      const rect = at === undefined ? boundingRect(form) : keptRects[at];
      const visible = styleHidden.has(form) ? isVisible(form, rect) : false;
      return {
        index,
        method: (getAttribute(form, "method") || "get").toLowerCase(),
        action: readFormAction.call(form),
        // :invalid does not fire invalid listeners. form.checkValidity is skipped
        // because a control named checkValidity replaces the method.
        valid: !elementMatches(form, ":invalid"),
        html_id: elementId(form) || null,
        visible,
        hidden: flagHidden.get(form) === true || !visible,
        inert: flagInert.get(form) === true,
        covered: at !== undefined && covered[at] === true,
        disabled: fieldsetDisabled(form),
      };
    },
  );

  const modals = [];
  const seen = new Set();
  const modalRoles = new Map();
  function pushModal(el, role) {
    if (seen.has(el) || !isVisible(el, boundingRect(el))) {
      return;
    }
    seen.add(el);
    modals.push(el);
    modalRoles.set(el, role);
  }
  for (const dialog of collectMatching("dialog[open]")) {
    if (elementMatches(dialog, ":modal")) {
      pushModal(dialog, "dialog");
    }
  }
  for (const dialog of collectMatching(
    "[role='dialog'][aria-modal='true'], [role='alertdialog'][aria-modal='true']",
  )) {
    pushModal(dialog, clean(getAttribute(dialog, "role")).split(" ")[0] || "dialog");
  }
  topModalEl = topmostModal(modals);
  const modalRecords = modals.map((el) => ({
    html_id: elementId(el) || null,
    role: modalRoles.get(el) || "dialog",
    name: accName(el),
    open: true,
    top: el === topModalEl,
  }));

  // Stringify in slices so a late clock keeps the rows already copied.
  // Each piece is one JSON array. Python reads them one at a time and stops
  // while the rows can still be built before the deadline.
  const chunks = [];
  let batch = [];
  const chunkRows = 800;
  // Object ids feed the accessibility overlay. The cap stays, but the slots
  // go to on-screen widgets first so a long link list cannot crowd them out.
  const nodeCap = 160;
  const widgetTags = new Set(["button", "input", "select", "textarea", "summary", "option"]);
  const widgetRoles = new Set([
    "button",
    "checkbox",
    "combobox",
    "gridcell",
    "listbox",
    "menu",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "radio",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textbox",
    "treeitem",
  ]);
  const ranked = [];
  for (let index = 0; index < kept.length; index += 1) {
    const el = kept[index];
    const tag = localName(el);
    const role = elementRole(el);
    const widget = widgetTags.has(tag) || widgetRoles.has(role);
    const link = tag === "a" || role === "link";
    if (!widget && !link) {
      continue;
    }
    const visible = isVisible(el, keptRects[index]);
    let rank = 3;
    if (widget && visible && inViewport(keptRects[index])) {
      rank = 0;
    } else if (widget) {
      rank = 1;
    } else if (visible) {
      rank = 2;
    }
    ranked.push({ index, rank });
  }
  ranked.sort((left, right) => left.rank - right.rank || left.index - right.index);
  const nodeIndexes = [];
  for (let index = 0; index < ranked.length && nodeIndexes.length < nodeCap; index += 1) {
    const at = ranked[index].index;
    nodeIndexes.push(at);
    nodes.push(kept[at]);
  }
  const axCapped = ranked.length > nodeCap;
  for (let index = 0; index < kept.length; index += 1) {
    if (index > 0 && pastReadback()) {
      truncated = true;
      break;
    }
    if (!cssOf(kept[index])) {
      truncated = true;
      break;
    }
    batch.push(elementRow(kept[index], keptRects[index], covered[index]));
    if (batch.length === chunkRows) {
      if (pastReadback()) {
        truncated = true;
        break;
      }
      chunks.push(JSON.stringify(batch));
      batch = [];
    }
  }
  if (batch.length > 0) {
    chunks.push(JSON.stringify(batch));
  }
  // No rows from a page that has controls is a deadline. Truncation does
  // not make an empty transfer a successful prefix.
  if (chunks.length === 0 && matched.length > 0) {
    return deadlinePayload();
  }

  return {
    meta: JSON.stringify({
      fields,
      forms,
      modals: modalRecords,
      url: pageUrl,
      title: pageTitle,
      truncated,
      deadline: false,
      chunks: chunks.length,
      controls: matched.length,
      indexed: indexFinished,
      node_indexes: nodeIndexes,
      ax_capped: axCapped,
    }),
    chunks,
    nodes,
  };
})()
