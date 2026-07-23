/**
 * app.js — UI logic for the XB12 Instructional-Materials Registry.
 * Depends on API (api.js) for all backend calls.
 */
(function () {
  'use strict';

  // ---- Small DOM helpers --------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
    );

  let currentCourse = null;

  // Map common De Anza course prefixes to full subject names so the subject
  // field can be pre-filled from the course entered in Step 1. Unknown
  // prefixes fall back to whatever the professor typed.
  const SUBJECT_BY_PREFIX = {
    ACCT: 'Accounting',
    ADMJ: 'Administration of Justice',
    AFAM: 'African American Studies',
    ANTH: 'Anthropology',
    ARTS: 'Visual Arts and Design',
    ASAM: 'Asian American and Asian Studies',
    ASTR: 'Astronomy',
    BIOL: 'Biology',
    BUS: 'Business',
    CD: 'Child Development',
    CETH: 'Comparative Ethnic Studies',
    CHLX: 'Chicanx/Latinx Studies',
    CIS: 'Computer Science and Information Systems',
    CLP: 'Career Life Planning',
    COMM: 'Communication Studies',
    ECON: 'Economics',
    ENGL: 'English',
    ES: 'Environmental Studies',
    ESCI: 'Environmental Science',
    ESL: 'English as a Second Language',
    EWRT: 'English Writing',
    'F/TV': 'Film and Television',
    GEO: 'Geography',
    GEOL: 'Geology and Oceanography',
    HIST: 'History',
    HLTH: 'Health',
    HTEC: 'Health Technologies',
    HUMA: 'Human Development',
    HUMI: 'Humanities',
    ICS: 'Intercultural Studies',
    JOUR: 'Journalism',
    KNES: 'Kinesiology',
    MAND: 'Mandarin',
    MATH: 'Mathematics',
    MET: 'Meteorology',
    MUSI: 'Music',
    NAIS: 'Native American and Indigenous Studies',
    NURS: 'Nursing',
    NUTR: 'Nutrition',
    PARA: 'Paralegal Program',
    PHIL: 'Philosophy',
    PHTG: 'Photography',
    PHYS: 'Physics',
    POLI: 'Political Science',
    POLS: 'Political Science',
    PSYC: 'Psychology',
    REST: 'Real Estate',
    SOC: 'Sociology',
    SOSC: 'Social Science',
    SPAN: 'Spanish',
    STAT: 'Statistics',
    THEA: 'Theatre Arts',
    WMST: "Women's Studies",
  };

  // OER publisher/source markers - mirrors the backend so the form can
  // preselect the OER cost type for OpenStax/LibreTexts/etc.
  const OER_MARKERS = [
    'openstax', 'libretext', 'pressbooks', 'oercommons', 'oer commons',
    'open education', 'open textbook', 'opentextbook', 'creative commons',
    'merlot', 'saylor', 'open.umn.edu',
  ];
  function looksLikeOER() {
    const hay = Array.prototype.slice.call(arguments).filter(Boolean).join(' ').toLowerCase();
    return OER_MARKERS.some((m) => hay.includes(m));
  }

  // Shorten a URL for display (drop protocol/trailing slash, cap length).
  function shortenUrl(url, max) {
    max = max || 48;
    let s = String(url || '').replace(/^https?:\/\//i, '').replace(/\/+$/, '');
    if (s.length > max) s = s.slice(0, max - 1) + '…';
    return s;
  }

  // Render a URL as a shortened, clickable link (full URL in title + href).
  function urlLink(url) {
    return `<a class="ai-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer" title="${esc(url)}">${esc(shortenUrl(url))}</a>`;
  }

  function subjectFromCourse() {
    if (!currentCourse) return '';
    const prefix = (currentCourse.coursePrefix || '').toUpperCase();
    return SUBJECT_BY_PREFIX[prefix] || currentCourse.coursePrefix || '';
  }

  // Pre-fill the resource subject from the loaded course. By default only fills
  // an empty field (so a manual edit isn't clobbered); pass force=true to reset.
  function prefillSubject(force) {
    const el = $('res-subject');
    if (!el) return;
    if (force || !el.value.trim()) el.value = subjectFromCourse();
  }

  // ---- XB12 presentation --------------------------------------------------
  const XB12_MEANING = {
    A: 'No associated course material',
    C: 'Course material costs, none passed to students',
    D: 'Low course material cost (LTC)',
    E: 'Only no-cost OER material (ZTC)',
    F: 'Only no-cost digital, non-OER material',
    G: 'Mix of OER and other resources, no cost to student',
    Y: 'Does not meet no-cost or low-cost criteria',
  };

  function xb12BadgeClass(code) {
    if (['E', 'F', 'G', 'C'].includes(code)) return 'xb12-ztc';
    if (code === 'D') return 'xb12-ltc';
    if (code === 'Y') return 'xb12-y';
    return 'xb12-none';
  }

  function xb12Badge(code, status) {
    if (!code) return '';
    const cls = xb12BadgeClass(code);
    const meaning = XB12_MEANING[code] || '';
    const statusChip = status
      ? ` <span class="xb12-status" title="Cost status">${esc(status)}</span>`
      : '';
    return `<span class="xb12-badge ${cls}" title="XB12 ${esc(code)}: ${esc(meaning)}"><span class="code">${esc(
      code
    )}</span> XB12</span>${statusChip}`;
  }

  // ---- Alerts -------------------------------------------------------------
  function showGlobalError(msg) {
    const el = $('global-alert');
    el.className = 'alert alert-error';
    el.textContent = msg;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function showGlobalSuccess(html) {
    const el = $('global-alert');
    el.className = 'alert alert-success';
    el.innerHTML = html;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function clearGlobalError() {
    $('global-alert').classList.add('hidden');
  }
  function setStatus(id, kind, html) {
    const el = $(id);
    el.className = `alert alert-${kind}`;
    el.innerHTML = html;
    el.classList.remove('hidden');
  }
  function hide(id) {
    $(id).classList.add('hidden');
  }

  // ---- Step locking -------------------------------------------------------
  function unlockCourseSteps() {
    $('step-adopted').classList.remove('locked');
    $('step-add').classList.remove('locked');
  }

  // =========================================================================
  // Step 1 — load course
  // =========================================================================
  async function loadCourse() {
    clearGlobalError();
    const prefix = $('course-prefix').value.trim().toUpperCase();
    const number = $('course-number').value.trim();
    const crn = $('crn').value.trim();
    if (!prefix || !number) {
      showGlobalError('Please enter both a course prefix and course number.');
      return;
    }
    if (!crn) {
      showGlobalError('Please enter a CRN — it identifies the section and is required to add materials.');
      $('crn').focus();
      return;
    }
    currentCourse = {
      coursePrefix: prefix,
      courseNumber: number,
      crn: $('crn').value.trim(),
      section: $('section').value.trim(),
      quarter: $('quarter').value.trim(),
      year: $('year').value.trim(),
      professorFirstName: $('prof-first').value.trim(),
      professorLastName: $('prof-last').value.trim(),
    };

    const term = [currentCourse.quarter, currentCourse.year].filter(Boolean).join(' ');
    const sectionLabel = currentCourse.section ? ` §${currentCourse.section}` : '';
    const crnLabel = currentCourse.crn ? ` · CRN ${currentCourse.crn}` : '';
    $('adopted-course-label').textContent =
      `${prefix} ${number}${sectionLabel}${term ? ' · ' + term : ''}${crnLabel}`;

    unlockCourseSteps();
    prefillSubject(true); // seed the add-new subject from the course
    // Seed the "use existing" class filter with this class (e.g. "ACCT 1A")
    // so prior-section materials for the same class surface immediately.
    const classEl = $('filter-class');
    if (classEl) classEl.value = `${prefix} ${number}`;
    await refreshAdopted();
    $('step-add').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function refreshAdopted() {
    if (!currentCourse) return;
    const listEl = $('adopted-list');
    listEl.innerHTML = '<p class="empty-hint"><span class="spinner dark"></span> Loading…</p>';
    try {
      const res = await API.listCourseResources({
        coursePrefix: currentCourse.coursePrefix,
        courseNumber: currentCourse.courseNumber,
        crn: currentCourse.crn,
        section: currentCourse.section,
        quarter: currentCourse.quarter,
        year: currentCourse.year,
      });
      renderAdopted(res.adoptions || []);
    } catch (e) {
      listEl.innerHTML = '';
      showGlobalError('Could not load current materials: ' + e.message);
    }
  }

  function renderAdopted(items) {
    const listEl = $('adopted-list');
    const emptyEl = $('adopted-empty');
    listEl.innerHTML = '';
    if (!items.length) {
      emptyEl.classList.remove('hidden');
      return;
    }
    emptyEl.classList.add('hidden');
    items
      .sort((a, b) => (b.adoptedAt || '').localeCompare(a.adoptedAt || ''))
      .forEach((it) => {
        const refHtml = it.ISBN
          ? `ISBN ${esc(it.ISBN)}`
          : it.url
          ? urlLink(it.url)
          : '';
        const div = document.createElement('div');
        div.className = 'adopted-item';
        div.innerHTML = `
          <div class="rc-main">
            <div class="ai-title">${esc(it.title || it.resourceId || 'Untitled resource')}</div>
            <div class="ai-meta">${esc(it.materialType || 'resource')}${refHtml ? ' · ' + refHtml : ''}</div>
          </div>
          <div class="rc-actions">
            ${xb12Badge(it.xb12Code, it.costStatus)}
            <button class="btn-remove-material" title="Remove this material" aria-label="Remove this material">Remove</button>
          </div>`;
        const btn = div.querySelector('.btn-remove-material');
        if (btn) btn.addEventListener('click', () => removeMaterial(it, btn));
        listEl.appendChild(div);
      });
  }

  async function removeMaterial(item, btn) {
    if (!item || !item.id) return;
    if (!window.confirm(`Remove "${item.title || 'this material'}" from this course?`)) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner dark"></span>';
    try {
      await API.deleteCourseResource(item.id);
      await refreshAdopted();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Remove';
      showGlobalError('Could not remove material: ' + e.message);
    }
  }

  // =========================================================================
  // Submit class — finalize with a section-level XB12 code
  // =========================================================================
  async function submitClass() {
    if (!currentCourse) {
      showGlobalError('Load a course first.');
      return;
    }
    const btn = $('btn-submit-class');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Submitting…';
    hide('submit-result');
    try {
      const res = await API.submitClass(currentCourse);
      const s = res.section || {};
      const verb = res.resubmitted ? 'updated' : 'submitted';
      const courseLabel = `${currentCourse.coursePrefix} ${currentCourse.courseNumber}` +
        (currentCourse.crn ? ` (CRN ${currentCourse.crn})` : '');
      // Confirm the submission in a persistent banner, then reset the form so
      // the next class can be entered from a clean slate.
      showGlobalSuccess(
        `${xb12Badge(s.code, res.submission && res.submission.sectionCostStatus)} ` +
        `<strong>${esc(courseLabel)}</strong> ${verb} — section XB12 code ` +
        `<strong>${esc(s.code || '')}</strong> (${esc(s.meaning || '')}). ` +
        `The form has been reset for the next class.`
      );
      resetForm();
    } catch (e) {
      setStatus('submit-status', 'error', 'Could not submit the class: ' + esc(e.message));
      btn.disabled = false;
      btn.innerHTML = original;
    }
  }

  // Clear the whole form after a submission so a new class can be entered.
  function resetForm() {
    currentCourse = null;
    ['course-prefix', 'course-number', 'crn', 'section', 'year', 'prof-first', 'prof-last']
      .forEach((id) => { if ($(id)) $(id).value = ''; });
    if ($('quarter')) $('quarter').value = '';

    // Search / filters
    ['search-q', 'filter-class', 'filter-subject'].forEach((id) => { if ($(id)) $(id).value = ''; });
    if ($('filter-xb12')) $('filter-xb12').value = '';
    if ($('filter-type')) $('filter-type').value = '';
    if ($('search-results')) $('search-results').innerHTML = '';
    if ($('search-status')) $('search-status').textContent = 'Enter a search above to find existing resources.';

    // Adopted materials + result panels
    if ($('adopted-list')) $('adopted-list').innerHTML = '';
    $('adopted-empty').classList.add('hidden');
    $('adopted-course-label').textContent = 'No course loaded yet.';
    hide('submit-result');
    hide('submit-status');
    resetNewForm();

    // Reset the submit button
    const submitBtn = $('btn-submit-class');
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Submit class';
    }

    // Re-lock the downstream steps until a new course is loaded
    $('step-adopted').classList.add('locked');
    $('step-add').classList.add('locked');

    const first = $('course-prefix');
    if (first) first.focus();
  }

  // =========================================================================
  // Step 2a — search existing
  // =========================================================================
  async function runSearch() {
    const statusEl = $('search-status');
    const resultsEl = $('search-results');
    resultsEl.innerHTML = '';
    statusEl.textContent = '';
    statusEl.innerHTML = '<span class="spinner dark"></span> Searching…';

    try {
      const res = await API.searchResources({
        q: $('search-q').value.trim(),
        className: $('filter-class').value.trim(),
        xb12: $('filter-xb12').value,
        materialType: $('filter-type').value,
        subject: $('filter-subject').value.trim(),
        size: 30,
      });
      const resources = res.resources || [];
      if (!resources.length) {
        statusEl.textContent = 'No matching resources found. Try the "Add new" tab.';
        return;
      }
      statusEl.textContent = `${res.count} result${res.count === 1 ? '' : 's'}`;
      resources.forEach((r) => resultsEl.appendChild(resourceCard(r)));
    } catch (e) {
      statusEl.textContent = '';
      showGlobalError('Search failed: ' + e.message);
    }
  }

  function resourceCard(r) {
    const meta = [];
    if (r.author) meta.push(esc(r.author));
    if (r.publisher) meta.push(esc(r.publisher));
    if (r.ISBN) meta.push('ISBN ' + esc(r.ISBN));
    if (r.url) meta.push(urlLink(r.url));
    if (r.materialType) meta.push(esc(r.materialType));

    const card = document.createElement('div');
    card.className = 'resource-card';
    card.innerHTML = `
      <div class="rc-main">
        <div class="rc-title">${esc(r.title || 'Untitled')}</div>
        <div class="rc-meta">${meta.join(' · ')}</div>
      </div>
      <div class="rc-actions">
        ${xb12Badge(r.xb12Code, r.costStatus)}
        <button class="btn-view">Add to course</button>
      </div>`;
    card.querySelector('button').addEventListener('click', () => adoptExisting(r, card));
    return card;
  }

  async function adoptExisting(r, card) {
    if (!currentCourse) {
      showGlobalError('Load a course first.');
      return;
    }
    const btn = card.querySelector('button');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
      await API.addCourseResource({
        ...currentCourse,
        resourceId: r.id,
        ISBN: r.ISBN,
        url: r.url,
        title: r.title,
        xb12Code: r.xb12Code,
        materialType: r.materialType,
        costType: r.costType,
        costStatus: r.costStatus,
        price: r.price,
      });
      btn.textContent = 'Added ✓';
      await refreshAdopted();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Add to course';
      showGlobalError('Could not add resource: ' + e.message);
    }
  }

  // =========================================================================
  // Step 2b — add new
  // =========================================================================
  function currentNewType() {
    const el = document.querySelector('input[name="new-type"]:checked');
    return el ? el.value : 'textbook';
  }

  function onNewTypeChange() {
    const type = currentNewType();
    $('new-textbook').classList.toggle('hidden', type !== 'textbook');
    $('new-platform').classList.toggle('hidden', type !== 'platform');
    hide('xb12-preview');
  }

  function onCostTypeChange() {
    const type = $('res-cost-type').value;
    const priced = type === 'priced' || type === 'subsidized';
    $('fg-price').style.opacity = priced ? '1' : '0.5';
    $('price-flag').textContent = type === 'priced' ? 'required' : '';
  }

  function markMissing(groupId, missing) {
    $(groupId).classList.toggle('field-missing', missing);
  }

  async function runIsbnLookup() {
    const isbn = $('isbn-input').value.trim();
    if (!isbn) {
      setStatus('isbn-status', 'warn', 'Please enter an ISBN.');
      return;
    }
    const btn = $('btn-isbn-lookup');
    btn.disabled = true;
    const original = btn.textContent;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await API.isbnLookup(isbn);
      const m = res.metadata || {};
      $('res-title').value = m.title || '';
      $('res-author').value = m.author || '';
      $('res-publisher').value = m.publisher || '';
      // Only use the book's category if the subject wasn't already set from
      // the course (course subject takes precedence).
      if (!$('res-subject').value.trim() && m.categories && m.categories.length) {
        $('res-subject').value = m.categories[0];
      }
      if (m.price != null) {
        $('res-price').value = m.price;
        $('res-cost-type').value = 'priced';
        onCostTypeChange();
      }

      const missing = res.missingFields || [];
      const bibMissing = missing.filter((f) => f !== 'price');
      const priceMissing = missing.includes('price');

      // OpenStax/LibreTexts/etc. are free OER -> preselect the OER cost type
      // and don't treat the missing price as something to fill in.
      const oer = looksLikeOER(m.title, m.author, m.publisher);
      if (oer) {
        $('res-cost-type').value = 'oer';
        onCostTypeChange();
      }

      markMissing('fg-title', bibMissing.includes('title'));
      markMissing('fg-author', bibMissing.includes('author'));
      markMissing('fg-publisher', bibMissing.includes('publisher'));
      markMissing('fg-price', priceMissing && !oer);

      // Price is rarely available from the free registries, so fall back to
      // manual entry: default a (non-OER) textbook to "priced" and flag the
      // price field as required so it's obvious the user needs to type it in.
      if (priceMissing && m.price == null && currentNewType() === 'textbook' && !oer) {
        $('res-cost-type').value = 'priced';
        onCostTypeChange();
      }

      if (!res.found) {
        setStatus(
          'isbn-status',
          'warn',
          'No registry match for that ISBN. Please fill in the details manually, including the price.'
        );
      } else {
        const src = esc((res.sources || []).join(', '));
        const parts = [];
        if (bibMissing.length) {
          parts.push(`complete the highlighted field(s): <strong>${esc(bibMissing.join(', '))}</strong>`);
        }
        if (priceMissing && !oer) {
          parts.push(
            'enter the <strong>price</strong> manually (or change the cost type if the material is free/OER)'
          );
        }
        if (oer) {
          parts.push('recognized as a free <strong>OER</strong> source (no price needed)');
        }
        if (parts.length) {
          setStatus('isbn-status', 'warn', `Found title &amp; author via ${src}. Please ${parts.join(' and ')}.`);
        } else {
          setStatus('isbn-status', 'success', `Details found via ${src}. Review and save below.`);
        }
      }
    } catch (e) {
      setStatus('isbn-status', 'error', 'Lookup failed: ' + esc(e.message));
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  async function saveNew() {
    if (!currentCourse) {
      showGlobalError('Load a course first.');
      return;
    }
    hide('xb12-preview');
    const type = currentNewType();
    const title = $('res-title').value.trim();
    const costType = $('res-cost-type').value;
    const priceRaw = $('res-price').value.trim();

    // Validation
    if (!title) {
      setStatus('new-status', 'warn', 'A title is required.');
      markMissing('fg-title', true);
      return;
    }
    const payload = {
      title,
      materialType: type,
      author: $('res-author').value.trim(),
      publisher: $('res-publisher').value.trim(),
      subject: $('res-subject').value.trim(),
      costType,
    };
    if (type === 'textbook') {
      const isbn = $('isbn-input').value.trim();
      if (!isbn) {
        setStatus('new-status', 'warn', 'Textbooks require an ISBN.');
        return;
      }
      payload.ISBN = isbn;
    } else {
      const url = $('platform-url').value.trim();
      if (!url) {
        setStatus('new-status', 'warn', 'Learning platforms require a URL.');
        return;
      }
      payload.url = url;
    }
    if (costType === 'priced' && !priceRaw) {
      setStatus('new-status', 'warn', 'Please enter the price the student pays.');
      return;
    }
    if (priceRaw) payload.price = priceRaw;

    const btn = $('btn-save-new');
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Saving…';
    try {
      const created = await API.createResource(payload);
      const xb = created.xb12 || {};
      // Adopt into the current course.
      await API.addCourseResource({
        ...currentCourse,
        resourceId: created.resource.id,
        ISBN: created.resource.ISBN,
        url: created.resource.url,
        title: created.resource.title,
        xb12Code: xb.code,
        materialType: created.resource.materialType,
        costType: created.resource.costType,
        costStatus: created.resource.costStatus,
        price: created.resource.price,
      });

      const previewEl = $('xb12-preview');
      previewEl.innerHTML = `
        <h3>XB12 classification</h3>
        <div>${xb12Badge(xb.code)} <strong>${esc(xb.code || '')}</strong> — ${esc(
        xb.meaning || ''
      )}${xb.ztcLtc ? ` <span class="chip chip-ztc">${esc(xb.ztcLtc)}</span>` : ''}</div>
        <p class="explain">${esc(xb.explanation || '')}</p>`;
      previewEl.classList.remove('hidden');

      setStatus('new-status', 'success', `"${esc(title)}" saved and added to your course.`);
      resetNewForm();
      await refreshAdopted();
    } catch (e) {
      showGlobalError('Could not save resource: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  }

  function resetNewForm() {
    ['isbn-input', 'platform-url', 'res-title', 'res-author', 'res-publisher', 'res-subject', 'res-price'].forEach(
      (id) => {
        if ($(id)) $(id).value = '';
      }
    );
    ['fg-title', 'fg-author', 'fg-publisher', 'fg-price'].forEach((g) => markMissing(g, false));
    hide('isbn-status');
    prefillSubject(true); // keep the course subject seeded for the next entry
  }

  // ---- Tabs ---------------------------------------------------------------
  function initTabs() {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
        tab.classList.add('active');
        $('panel-' + tab.dataset.tab).classList.add('active');
      });
    });
  }

  // ---- Wire up ------------------------------------------------------------
  async function init() {
    await API.initConfig();
    initTabs();
    onNewTypeChange();
    onCostTypeChange();

    // The Add-resource / search fields must start empty until a course is
    // loaded (guards against browser autofill or form restoration).
    [
      'isbn-input', 'platform-url', 'res-title', 'res-author', 'res-publisher',
      'res-subject', 'res-price', 'search-q', 'filter-class', 'filter-subject',
    ].forEach((id) => { if ($(id)) $(id).value = ''; });

    $('btn-load-course').addEventListener('click', loadCourse);
    $('btn-search').addEventListener('click', runSearch);
    $('search-q').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runSearch();
    });
    $('btn-isbn-lookup').addEventListener('click', runIsbnLookup);
    $('isbn-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runIsbnLookup();
      }
    });
    $('btn-save-new').addEventListener('click', saveNew);
    $('btn-submit-class').addEventListener('click', submitClass);
    $('res-cost-type').addEventListener('change', onCostTypeChange);
    document.querySelectorAll('input[name="new-type"]').forEach((r) =>
      r.addEventListener('change', onNewTypeChange)
    );
  }

  document.addEventListener('DOMContentLoaded', init);
})();
