# Accessibility Conformance Checklist — IS 17802 Parts 1 & 2 / WCAG 2.1 AA

**System:** Pre-NPA Rescue (Frontend `apps/web`)  
**Standard:** IS 17802 (Part 1):2021 & (Part 2):2022 (ICT Accessibility Requirements), aligned with WCAG 2.1 AA.  
**Auditor Workstream:** WS6 (Frontend) & WS7 (Governance & Red Team).

---

## 1. Conformance Matrix

| Principle & Guideline | IS 17802 Clause | Implementation in Pre-NPA Rescue Web App | Status |
|---|---|---|---|
| **Non-text Content** | 9.1.1.1 | All icons have `aria-hidden="true"`, buttons and interactive elements provide explicit `aria-label` or accessible text. | Conforming |
| **Contrast (Minimum)** | 9.1.4.3 | All text elements achieve ≥ 4.5:1 contrast against background in both light and dark modes (measured with teal/slate theme tokens). | Conforming |
| **Resize Text** | 9.1.4.4 | Layout scales up to 200% without loss of content or functionality using relative units (`rem`, `px` grid). | Conforming |
| **Keyboard Operable** | 9.2.1.1 | All controls (role picker, language switcher, buttons, links) operable via `Tab`, `Shift+Tab`, `Enter`, and `Space`. | Conforming |
| **No Keyboard Trap** | 9.2.1.2 | No focus traps exist in the navigation or demo cards. | Conforming |
| **Focus Visible** | 9.2.4.7 | Explicit 2px ring with offset (`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2`) defined in `app/globals.css`. | Conforming |
| **Bypass Blocks** | 9.2.4.1 | Skip-to-content link provided at the very top of `AppShell.tsx` targeting `#main-content`. | Conforming |
| **Language of Page** | 9.3.1.1 | `<html>` tag sets `lang="en"`, `lang="ta"`, or `lang="hi"` dynamically based on active route. | Conforming |
| **Language of Parts** | 9.3.1.2 | Language switch buttons and multilingual reason texts include localized `lang` attributes. | Conforming |
| **Status Messages** | 9.4.1.3 | Error envelopes use `role="alert"`; loading skeletons use `role="status"` with screen-reader text; live regions defined for async updates. | Conforming |
| **Reduced Motion** | 9.2.2.2 | CSS `@media (prefers-reduced-motion: reduce)` disables animations and smooth transitions across all components. | Conforming |
| **Color Meaning** | 9.1.4.1 | Information is never conveyed by color alone; all risk, bucket, segment, and uplift badges include explicit text labels and semantic icons. | Conforming |

---

## 2. Keyboard Walkthrough Protocol (IS 17802 Part 2)

### Flow 1: Role Selection & Persona Switching
1. **Initial Tab:** Focuses the "Skip to main content" link. Pressing Enter moves focus immediately to `#main-content`.
2. **Top Bar:** Focus moves to Brand Link, then Language Switcher (EN / தமிழ் / हिंदी buttons with `aria-pressed`), then Role/Logout button if logged in.
3. **Hero & Cards:** Focus enters the Persona Cards in sequential order:
   - Priya (Customer — Tamil)
   - Ravi (Customer — English Zero Capacity)
   - Collector
   - Hardship Officer
   - Bank Administrator
   - Compliance Auditor
4. **Action Button:** Pressing `Enter` or `Space` triggers the action button with immediate visual and programmatic feedback.
