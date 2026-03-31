// FieldFlow Edge Function: treetime-projects
// Deploy to your FieldFlow Supabase project:
//   supabase functions deploy treetime-projects
//
// Set the API key secret:
//   supabase secrets set TREETIME_API_KEY=kRLmwR4APa6x4Tkz0iFouOzYLMS8OxYI
//
// File location in FieldFlow repo:
//   supabase/functions/treetime-projects/index.ts

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-api-key, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  // ── Auth: check API key ──────────────────────────────────────────
  const apiKey = req.headers.get("x-api-key");
  const expectedKey = Deno.env.get("TREETIME_API_KEY");

  if (!expectedKey || apiKey !== expectedKey) {
    return new Response(
      JSON.stringify({ error: "Unauthorized" }),
      { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  // ── Parse query params ───────────────────────────────────────────
  const url = new URL(req.url);
  const activeOnly = url.searchParams.get("active_only") !== "false";
  const workspaceId = url.searchParams.get("workspace_id");

  // ── Query projects ───────────────────────────────────────────────
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const supabase = createClient(supabaseUrl, supabaseKey);

  let query = supabase
    .from("projects")
    .select(`
      id,
      project_number,
      title,
      status,
      clients (
        name,
        company
      )
    `)
    .order("project_number", { ascending: true });

  // Filter by status if active_only
  if (activeOnly) {
    query = query.not("status", "in", '("completed","cancelled")');
  }

  // Filter by workspace if provided
  if (workspaceId) {
    query = query.eq("workspace_id", workspaceId);
  }

  const { data, error } = await query;

  if (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }

  // ── Shape response ───────────────────────────────────────────────
  const projects = (data || []).map((p: any) => ({
    id: p.id,
    project_number: p.project_number,
    title: p.title,
    status: p.status,
    client_name: p.clients?.name || "",
    client_company: p.clients?.company || "",
    keyword: p.project_number,
  }));

  return new Response(
    JSON.stringify({ projects, count: projects.length }),
    { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
  );
});
