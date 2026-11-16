-- Banco Magallanes banking core: schema.
-- Run once in the Supabase SQL editor. Safe to run again: nothing is dropped.
--
-- Every table has row level security enabled and no policies, so the public
-- API keys can read nothing. Only the server-side secret key, which bypasses
-- row level security, can read or write.

create table if not exists customers (
    id uuid primary key default gen_random_uuid(),
    document_type text not null check (document_type in ('RUT', 'DNI', 'CC', 'CURP')),
    document_number text not null unique,
    first_name text not null,
    last_name text not null,
    birth_date date not null,
    email text not null,
    phone text,
    telegram_chat_id text,
    country text not null,
    preferred_language text not null default 'es',
    segment text not null check (segment in ('mass', 'preferred', 'premium')),
    is_vulnerable boolean not null default false,
    -- The bank's app: a hashed PIN, and a short lock after three wrong attempts.
    app_pin_hash text,
    app_failed_pins integer not null default 0,
    app_locked_until timestamptz
);

create table if not exists accounts (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references customers (id),
    type text not null check (type in ('checking', 'sight', 'savings')),
    currency text not null,
    available_balance numeric(14, 2) not null,
    updated_at timestamptz not null default now()
);

create table if not exists cards (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references customers (id),
    last4 text not null,
    brand text not null,
    type text not null check (type in ('credit', 'debit')),
    status text not null default 'active'
        check (status in ('active', 'blocked_temporary', 'blocked')),
    daily_limit numeric(14, 2) not null,
    blocked_at timestamptz,
    block_reason text
);

-- No merchant name on purpose: a statement shows a descriptor and sometimes a tax ID.
create table if not exists transactions (
    id uuid primary key default gen_random_uuid(),
    card_id uuid not null references cards (id),
    amount numeric(14, 2) not null,
    currency text not null,
    original_amount numeric(14, 2),
    original_currency text,
    descriptor text not null,
    merchant_tax_id text,
    mcc text,
    channel text not null check (channel in ('pos', 'ecommerce')),
    country text not null,
    transaction_at timestamptz not null,
    posted_at timestamptz,
    status text not null check (status in ('pending', 'posted', 'reversed')),
    is_disputed boolean not null default false
);

create table if not exists insurance_products (
    code text primary key,
    name text not null,
    monthly_premium numeric(14, 2) not null,
    currency text not null,
    coverage_summary text not null,
    eligible_segments text[] not null,
    active boolean not null default true
);

create table if not exists policies (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references customers (id),
    product_code text not null references insurance_products (code),
    policy_number text unique,
    proposal_id uuid,
    status text not null default 'active' check (status in ('active', 'cancelled')),
    started_at timestamptz not null default now()
);

-- One row per offer made. This table is the consent record.
create table if not exists insurance_offers (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references customers (id),
    product_code text not null references insurance_products (code),
    conversation_id text,
    customer_response text not null
        check (customer_response in ('accepted', 'declined', 'info_requested')),
    created_at timestamptz not null default now()
);

create table if not exists proposals (
    id uuid primary key default gen_random_uuid(),
    offer_id uuid not null references insurance_offers (id),
    customer_id uuid not null references customers (id),
    product_code text not null references insurance_products (code),
    proposal_number text not null unique,
    signing_token text unique,
    status text not null default 'sent' check (status in ('sent', 'signed', 'expired')),
    sent_to text not null,
    created_at timestamptz not null default now(),
    viewed_at timestamptz,
    signed_at timestamptz
);

-- The price and limit the bank quotes one customer for one product. Valid 15 days.
create table if not exists quotes (
    id uuid primary key default gen_random_uuid(),
    quote_number text not null unique,
    customer_id uuid not null references customers (id),
    product_code text not null references insurance_products (code),
    monthly_premium numeric(14, 2) not null,
    currency text not null,
    coverage_limit numeric(14, 2) not null,
    created_at timestamptz not null default now(),
    valid_until timestamptz not null
);

-- Columns added after the first release. A database created by an earlier
-- version of this file gets them here; on a new database these lines do nothing.
alter table policies add column if not exists policy_number text unique;
alter table customers add column if not exists app_pin_hash text;
alter table customers add column if not exists app_failed_pins integer not null default 0;
alter table customers add column if not exists app_locked_until timestamptz;
alter table policies add column if not exists proposal_id uuid;
alter table proposals add column if not exists viewed_at timestamptz;
alter table insurance_offers add column if not exists quote_number text;
alter table proposals add column if not exists quote_number text;

-- A policy points back to the proposal the customer signed. Added here because
-- `policies` is created before `proposals`.
alter table policies drop constraint if exists policies_proposal_fk;
alter table policies add constraint policies_proposal_fk
    foreign key (proposal_id) references proposals (id);

-- Case numbers look like MG-2026-000001: prefix, year, then this sequence.
create sequence if not exists case_number_seq;

create table if not exists cases (
    id uuid primary key default gen_random_uuid(),
    case_number text not null unique default (
        'MG-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('case_number_seq')::text, 6, '0')
    ),
    customer_id uuid references customers (id),
    type text not null check (type in ('fraud', 'handoff', 'complaint', 'callback')),
    priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
    status text not null default 'open' check (status in ('open', 'closed')),
    summary text not null,
    transaction_ids uuid[] not null default '{}',
    conversation_id text,
    crm_reference text,
    callback_window text,
    created_at timestamptz not null default now()
);

create table if not exists verification_sessions (
    id uuid primary key default gen_random_uuid(),
    token text not null unique,
    customer_id uuid not null references customers (id),
    conversation_id text,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);

create table if not exists verification_attempts (
    id uuid primary key default gen_random_uuid(),
    document_number text not null,
    success boolean not null,
    conversation_id text,
    created_at timestamptz not null default now()
);

-- A request to confirm identity in the bank's app. Pending for 90 seconds.
-- customer_id is null when the document is unknown: the request then just expires.
create table if not exists identity_confirmations (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid references customers (id),
    document_number text not null,
    code text not null,
    status text not null default 'pending' check (status in ('pending', 'approved', 'denied')),
    conversation_id text,
    session_token text,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    decided_at timestamptz
);

-- A signed-in session of the bank's app, opened with the PIN. Ten minutes.
create table if not exists app_sessions (
    id uuid primary key default gen_random_uuid(),
    token text not null unique,
    customer_id uuid not null references customers (id),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);

create table if not exists audit_log (
    id uuid primary key default gen_random_uuid(),
    at timestamptz not null default now(),
    endpoint text not null,
    method text not null,
    customer_id uuid references customers (id),
    conversation_id text,
    outcome text not null,
    detail jsonb not null default '{}'
);

-- Stand-in for the public company registry: who is behind a merchant tax ID.
create table if not exists registry_merchants (
    tax_id text primary key,
    legal_name text not null,
    trade_name text not null,
    activity text not null,
    address text not null,
    commune text not null,
    country text not null
);

create index if not exists accounts_customer_idx on accounts (customer_id);
create index if not exists cards_customer_idx on cards (customer_id);
create index if not exists transactions_card_idx on transactions (card_id, transaction_at desc);
create index if not exists policies_customer_idx on policies (customer_id);
create index if not exists offers_customer_idx on insurance_offers (customer_id);
create index if not exists quotes_customer_idx on quotes (customer_id);
create index if not exists cases_customer_idx on cases (customer_id);
create index if not exists attempts_document_idx
    on verification_attempts (document_number, created_at desc);
create index if not exists confirmations_customer_idx
    on identity_confirmations (customer_id, created_at desc);
create index if not exists audit_at_idx on audit_log (at desc);

alter table customers enable row level security;
alter table accounts enable row level security;
alter table cards enable row level security;
alter table transactions enable row level security;
alter table insurance_products enable row level security;
alter table policies enable row level security;
alter table insurance_offers enable row level security;
alter table quotes enable row level security;
alter table proposals enable row level security;
alter table cases enable row level security;
alter table verification_sessions enable row level security;
alter table verification_attempts enable row level security;
alter table identity_confirmations enable row level security;
alter table app_sessions enable row level security;
alter table audit_log enable row level security;
alter table registry_merchants enable row level security;

-- The server-side key acts as the service_role database role.
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
