-- Radar Salud V2 - PostgreSQL / Supabase
-- Core product: DISCOVER · WATCH · CONNECT · TREND · BENCHMARK · ASK

create extension if not exists pgcrypto;

create table if not exists sources (
  source_id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  source_type text not null,
  system_domain text,
  country_code text not null default 'CL',
  base_confidence integer not null check (base_confidence between 0 and 100),
  cadence text,
  method text,
  url text,
  enabled boolean not null default true,
  mvp_enabled boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists raw_items (
  raw_item_id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(source_id),
  external_id text,
  detected_at timestamptz not null default now(),
  event_date date,
  title text,
  url text,
  raw_text text,
  raw_payload jsonb not null default '{}'::jsonb,
  content_hash text,
  processed boolean not null default false,
  unique(source_id, external_id)
);

-- Canonical entities make cross-source matching possible.
create table if not exists entities (
  entity_id uuid primary key default gen_random_uuid(),
  canonical_name text not null,
  entity_type text not null default 'organization',
  institution_type text,
  subsector text,
  country_code text not null default 'CL',
  region text,
  ownership_type text,
  aliases text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  unique(canonical_name, country_code)
);

create table if not exists signals (
  signal_id uuid primary key default gen_random_uuid(),
  raw_item_id uuid references raw_items(raw_item_id),
  detected_at timestamptz not null default now(),
  event_date date,
  title text not null,

  source_id uuid references sources(source_id),
  source_name text not null,
  source_type text not null,
  source_url text,
  primary_source_url text,

  system_domain text,
  country_code text not null default 'CL',
  category text not null,             -- DISCOVER family
  subcategory text,
  event_type text not null default 'OTHER',
  institution_types text[] not null default '{}',
  strategic_themes text[] not null default '{}',
  topics text[] not null default '{}',
  entities_display text[] not null default '{}',
  people text[] not null default '{}',
  geography text[] not null default '{}',

  what_happened text not null,
  key_facts jsonb not null default '[]'::jsonb,
  key_numbers jsonb not null default '[]'::jsonb,
  why_it_matters text,
  who_cares text[] not null default '{}',
  possible_implications jsonb not null default '[]'::jsonb,

  -- Hints for graph/pattern layers.
  connection_keys text[] not null default '{}',
  trend_keys text[] not null default '{}',
  prospective_evidence boolean not null default false,

  economic_impact_score integer not null default 0,
  regulatory_impact_score integer not null default 0,
  scope_score integer not null default 0,
  novelty_score integer not null default 0,
  actionability_score integer not null default 0,
  source_quality_score integer not null default 0,
  radar_score integer not null default 0,
  confidence_score integer not null default 0,

  watch_tags text[] not null default '{}',
  distribution text not null default 'archive',
  validation_status text not null default 'automatic',
  corroboration_status text not null default 'unknown',
  additional_sources text[] not null default '{}',

  original_language text not null default 'es',
  display_language text not null default 'es',
  translation_status text not null default 'not_required',
  original_title text,
  original_what_happened text,
  original_why_it_matters text,

  created_by text not null default 'radar-engine',
  model_version text,
  created_at timestamptz not null default now()
);

create table if not exists signal_entities (
  signal_id uuid not null references signals(signal_id) on delete cascade,
  entity_id uuid not null references entities(entity_id) on delete cascade,
  role text,
  primary key(signal_id, entity_id)
);

-- CONNECT: explicit graph edges between atomic signals.
create table if not exists signal_connections (
  connection_id uuid primary key default gen_random_uuid(),
  signal_a_id uuid not null references signals(signal_id) on delete cascade,
  signal_b_id uuid not null references signals(signal_id) on delete cascade,
  relationship_type text not null,
  strength_score integer not null check (strength_score between 0 and 100),
  rationale text,
  shared_entities text[] not null default '{}',
  shared_themes text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique(signal_a_id, signal_b_id, relationship_type)
);

-- TREND: derived multi-signal patterns. Never stored as raw facts without evidence.
create table if not exists trends (
  trend_id uuid primary key default gen_random_uuid(),
  trend_key text not null,
  country_code text not null default 'CL',
  title text not null,
  strategic_theme text not null,
  status text not null check (status in ('emerging','accelerating','established','cooling')),
  window_days integer not null,
  signal_count integer not null,
  entity_count integer not null,
  current_intensity numeric not null,
  previous_intensity numeric not null,
  growth_pct numeric,
  momentum_score integer not null default 0 check (momentum_score between 0 and 100),
  confidence_score integer not null,
  why_it_matters text,
  institution_types text[] not null default '{}',
  entities_display text[] not null default '{}',
  prospective_flag boolean not null default false,
  prospective_confidence integer check (prospective_confidence between 0 and 100),
  projection_horizon_days integer,
  prospective_note text,
  detected_at timestamptz not null default now()
);

create table if not exists trend_signals (
  trend_id uuid not null references trends(trend_id) on delete cascade,
  signal_id uuid not null references signals(signal_id) on delete cascade,
  primary key(trend_id, signal_id)
);



-- BENCHMARK structured data layer: definitions are separated from observations.
create table if not exists metric_definitions (
  metric_id text primary key,
  name text not null,
  family text not null,
  institution_types text[] not null default '{}',
  unit text not null,
  description text not null,
  directionality text not null default 'neutral',
  aggregation text not null default 'latest',
  numerator_definition text,
  denominator_definition text,
  time_granularity text not null default 'periodic',
  comparable_across_entities boolean not null default true,
  segment_dimensions text[] not null default '{}',
  geography_levels text[] not null default '{}',
  source_preferences text[] not null default '{}',
  caveats text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists metric_observations (
  observation_id uuid primary key default gen_random_uuid(),
  entity_id uuid not null references entities(entity_id) on delete cascade,
  metric_id text not null references metric_definitions(metric_id),
  value numeric not null,
  unit text not null,
  period_start date not null,
  period_end date not null,
  country_code text not null default 'CL',
  institution_type text,
  geography text,
  population text,
  segment jsonb not null default '{}'::jsonb,
  source_name text not null,
  source_url text not null,
  source_id uuid references sources(source_id),
  confidence_score integer not null default 100 check (confidence_score between 0 and 100),
  is_estimated boolean not null default false,
  methodology_note text,
  retrieved_at timestamptz not null default now(),
  unique(entity_id, metric_id, period_end, geography, population, segment, source_url)
);

create index if not exists idx_metric_obs_metric_period on metric_observations(metric_id, period_end desc);
create index if not exists idx_metric_obs_entity_period on metric_observations(entity_id, period_end desc);
create index if not exists idx_metric_obs_segment on metric_observations using gin(segment);


-- WATCH: user-defined filters over the same universe, not separate Radars.
create table if not exists user_watchlists (
  watch_id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  label text,
  entities text[] not null default '{}',
  institution_types text[] not null default '{}',
  event_types text[] not null default '{}',
  strategic_themes text[] not null default '{}',
  topics text[] not null default '{}',
  geography text[] not null default '{}',
  immediate_alerts boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists idx_signals_event_date on signals(event_date desc);
create index if not exists idx_signals_radar_score on signals(radar_score desc);
create index if not exists idx_signals_category on signals(category);
create index if not exists idx_signals_event_type on signals(event_type);
create index if not exists idx_signals_topics on signals using gin(topics);
create index if not exists idx_signals_watch_tags on signals using gin(watch_tags);
create index if not exists idx_signals_strategic_themes on signals using gin(strategic_themes);
create index if not exists idx_signals_institution_types on signals using gin(institution_types);
create index if not exists idx_connections_a on signal_connections(signal_a_id);
create index if not exists idx_connections_b on signal_connections(signal_b_id);
create index if not exists idx_trends_key on trends(trend_key, detected_at desc);

-- Deliberately excluded from V2 core: community/Waze reports and private-data ANALYZE.
