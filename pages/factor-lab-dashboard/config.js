// GitHub Pages can only host the static dashboard. Set this to a deployed
// Flask base URL, for example "https://factor-lab-api.onrender.com".
window.FACTOR_LAB_API_HOST = "";

// Supabase public read endpoint for the static dashboard. This key is safe to
// expose only when Row Level Security allows SELECT on public dashboard tables.
window.FACTOR_LAB_SUPABASE_URL = "https://rebyrzrvnfbwvmbjvhzj.supabase.co";
window.FACTOR_LAB_SUPABASE_ANON_KEY = "sb_publishable_ZHAM5wQWZh_Wng4TaL-fDg_XlFBcB6j";
window.FACTOR_LAB_SUPABASE_FACTOR_TABLE = "public_dashboard_factors";
window.FACTOR_LAB_SUPABASE_TRUTH_SUMMARY_TABLE = "factor_truth_values_summary";

// Frontend-only access gate for the static dashboard. This is a convenience
// login screen, not a substitute for Supabase RLS or backend authentication.
window.FACTOR_LAB_ACCESS_PASSWORD = "factorlab2026";
