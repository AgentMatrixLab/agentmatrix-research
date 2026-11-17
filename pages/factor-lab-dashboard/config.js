// Factor Lab dashboard configuration.
//
// The dashboard reads its data from the Factor Lab API. Deployments that do not run
// that API on the same origin set `FACTOR_LAB_API_HOST` in `config.local.js`
// (gitignored; see config.local.example.js).
//
// --- Why there is no Supabase credential here any more -------------------------
// The dashboard used to read a Supabase mirror with a "publishable" anon key. That
// key was committed in a PUBLIC repository, and every policy on those tables is
// `for select to anon using (true)`, so anything written there is world-readable.
// That is fine for a public demo and unusable for a client deliverable: the client's
// factor verdicts, out-of-sample curves and NAV series cannot be access-controlled by
// a key everybody can read, and "client logs in with one password" has to be enforced
// by our own API.
//
// So the mirror is gone from the client path. The data now has exactly one
// authoritative home (the server's files) and one read path (the API). If a public
// showcase is ever wanted again, point it at the API's public read endpoints rather
// than reintroducing a second copy of the data.
//
// Any credential previously published here should be treated as compromised and
// disabled in the Supabase project.
window.FACTOR_LAB_SUPABASE_URL = "";
window.FACTOR_LAB_SUPABASE_ANON_KEY = "";
window.FACTOR_LAB_SUPABASE_FACTOR_TABLE = "public_dashboard_factors";
window.FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE = "factor_truth_values_summary";

// GitHub Pages uses the existing authenticated server API, not a data snapshot.
window.FACTOR_LAB_API_HOST = "https://factor.liangjun.net.cn";

// Convenience gate on the UI only. Real access control lives on the API: this value
// is served to every visitor, so it can keep honest users out but not attackers.
window.FACTOR_LAB_ACCESS_PASSWORD = "factorlab2026";
