-- ACIP database schema (reference only). Source of truth: backend/migrations (Alembic).
-- Generated with: docker compose exec -T postgres pg_dump --schema-only --no-owner --no-privileges -U acip acip --exclude-table='public.cost_records_2*'
-- Monthly partitions cost_records_YYYY_MM are created at runtime by the ingestion worker and are omitted.

--
-- PostgreSQL database dump
--

\restrict tzkkyNRhy9t1morrNf0R2AY7dSwuHqGBYeC7IwGzKkrMqcvS9Susj4sL9Doaee0

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alert_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_rules (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    alert_type character varying(64) NOT NULL,
    min_severity character varying(32),
    filters jsonb NOT NULL,
    params jsonb NOT NULL,
    channels jsonb NOT NULL,
    cooldown_hours integer NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alert_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alert_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alert_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alert_rules_id_seq OWNED BY public.alert_rules.id;


--
-- Name: anomaly_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.anomaly_events (
    id bigint NOT NULL,
    anomaly_id bigint NOT NULL,
    event_type character varying(32) NOT NULL,
    from_status character varying(32),
    to_status character varying(32),
    comment text,
    actor character varying(200) NOT NULL,
    details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: anomaly_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.anomaly_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: anomaly_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.anomaly_events_id_seq OWNED BY public.anomaly_events.id;


--
-- Name: anomaly_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.anomaly_rules (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    detection_type character varying(64) NOT NULL,
    scope_level character varying(64) NOT NULL,
    filters jsonb NOT NULL,
    params jsonb NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: anomaly_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.anomaly_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: anomaly_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.anomaly_rules_id_seq OWNED BY public.anomaly_rules.id;


--
-- Name: application_mappings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_mappings (
    id integer NOT NULL,
    match_type character varying(32) NOT NULL,
    pattern character varying(500) NOT NULL,
    subscription_fk integer,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    priority integer NOT NULL,
    enabled boolean NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: application_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.application_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: application_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.application_mappings_id_seq OWNED BY public.application_mappings.id;


--
-- Name: application_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_settings (
    key character varying(200) NOT NULL,
    value jsonb NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by character varying(200) NOT NULL
);


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    owner character varying(200),
    is_active boolean NOT NULL,
    is_demo boolean NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: applications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.applications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: applications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.applications_id_seq OWNED BY public.applications.id;


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id bigint NOT NULL,
    actor character varying(200) NOT NULL,
    actor_id character varying(200),
    action character varying(100) NOT NULL,
    entity_type character varying(64),
    entity_id character varying(200),
    details jsonb,
    ip_address character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: azure_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.azure_resources (
    id bigint NOT NULL,
    resource_key text NOT NULL,
    resource_id text NOT NULL,
    resource_name character varying(400),
    resource_type character varying(300),
    subscription_fk integer NOT NULL,
    resource_group character varying(200),
    region character varying(100),
    sku character varying(200),
    service_category character varying(100),
    tags jsonb,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32),
    owner character varying(200),
    cost_center character varying(200),
    first_seen_date date,
    last_seen_date date,
    is_demo boolean NOT NULL
);


--
-- Name: azure_resources_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.azure_resources_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: azure_resources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.azure_resources_id_seq OWNED BY public.azure_resources.id;


--
-- Name: azure_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.azure_subscriptions (
    id integer NOT NULL,
    subscription_id character varying(64) NOT NULL,
    subscription_name character varying(200) NOT NULL,
    application_id integer,
    environment_id integer,
    tenant_id character varying(64),
    billing_currency character varying(3) NOT NULL,
    enabled boolean NOT NULL,
    is_demo boolean NOT NULL,
    connection_status character varying(32) NOT NULL,
    auth_status character varying(32) NOT NULL,
    cost_api_status character varying(32) NOT NULL,
    storage_status character varying(32) NOT NULL,
    last_connection_test_at timestamp with time zone,
    connection_details jsonb,
    last_successful_sync_at timestamp with time zone,
    last_sync_attempt_at timestamp with time zone,
    last_sync_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: azure_subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.azure_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: azure_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.azure_subscriptions_id_seq OWNED BY public.azure_subscriptions.id;


--
-- Name: budgets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.budgets (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_ref character varying(300),
    period_type character varying(16) NOT NULL,
    amount numeric(28,10) NOT NULL,
    currency character varying(3) NOT NULL,
    cost_type character varying(32) NOT NULL,
    start_date date NOT NULL,
    end_date date,
    thresholds jsonb NOT NULL,
    forecast_alert boolean NOT NULL,
    enabled boolean NOT NULL,
    notes text,
    is_demo boolean NOT NULL,
    created_by character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: budgets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.budgets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: budgets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.budgets_id_seq OWNED BY public.budgets.id;


--
-- Name: cost_anomalies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_anomalies (
    id bigint NOT NULL,
    rule_id integer,
    rule_code character varying(64) NOT NULL,
    detection_type character varying(64) NOT NULL,
    category character varying(100) NOT NULL,
    scope_level character varying(64) NOT NULL,
    scope_key text NOT NULL,
    title character varying(400) NOT NULL,
    detected_at timestamp with time zone DEFAULT now() NOT NULL,
    detection_date date NOT NULL,
    last_detected_date date NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer,
    application_id integer,
    environment_id integer,
    service_category character varying(100),
    resource_group character varying(200),
    resource_key text,
    resource_name character varying(400),
    previous_cost numeric(28,10) NOT NULL,
    current_cost numeric(28,10) NOT NULL,
    expected_baseline numeric(28,10) NOT NULL,
    absolute_increase numeric(28,10) NOT NULL,
    percentage_increase numeric(28,10),
    severity character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    evidence jsonb NOT NULL,
    explanation text NOT NULL,
    recommended_steps jsonb NOT NULL,
    occurrence_count integer NOT NULL,
    is_demo boolean NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cost_anomalies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_anomalies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_anomalies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_anomalies_id_seq OWNED BY public.cost_anomalies.id;


--
-- Name: cost_comparisons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_comparisons (
    id bigint NOT NULL,
    name character varying(200) NOT NULL,
    params jsonb NOT NULL,
    created_by character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cost_comparisons_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_comparisons_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_comparisons_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_comparisons_id_seq OWNED BY public.cost_comparisons.id;


--
-- Name: cost_data_slices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_data_slices (
    subscription_fk integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    usage_date date NOT NULL,
    export_run_id bigint NOT NULL,
    run_submitted_at timestamp with time zone NOT NULL,
    row_count integer NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cost_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_records (
    id bigint NOT NULL,
    usage_date date NOT NULL,
    export_run_id bigint,
    ingestion_file_id bigint,
    source_row_number integer,
    billing_period_start date,
    billing_period_end date,
    cost numeric(28,10) NOT NULL,
    cost_usd numeric(28,10),
    payg_cost numeric(28,10),
    quantity numeric(28,10),
    unit_of_measure character varying(100),
    unit_price numeric(28,10),
    effective_price numeric(28,10),
    resource_id text,
    resource_key text NOT NULL,
    resource_name character varying(400),
    resource_group character varying(200),
    resource_type character varying(300),
    service_name character varying(200),
    service_family character varying(200),
    consumed_service character varying(200),
    meter_id character varying(100),
    meter_name character varying(300),
    meter_category character varying(200),
    meter_subcategory character varying(300),
    meter_region character varying(100),
    product_name character varying(400),
    sku character varying(200),
    frequency character varying(64),
    benefit_id character varying(300),
    benefit_name character varying(300),
    publisher_type character varying(64),
    source_cost_center character varying(200),
    tags jsonb,
    additional_info jsonb,
    extra jsonb,
    project character varying(200),
    team character varying(200),
    business_unit character varying(200),
    workload character varying(200),
    attribution_source character varying(200),
    normalizer_version character varying(32) NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
)
PARTITION BY RANGE (usage_date);


--
-- Name: cost_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cost_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cost_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cost_records_id_seq OWNED BY public.cost_records.id;


--
-- Name: cost_records_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_records_default (
    id bigint DEFAULT nextval('public.cost_records_id_seq'::regclass) NOT NULL,
    usage_date date NOT NULL,
    export_run_id bigint,
    ingestion_file_id bigint,
    source_row_number integer,
    billing_period_start date,
    billing_period_end date,
    cost numeric(28,10) NOT NULL,
    cost_usd numeric(28,10),
    payg_cost numeric(28,10),
    quantity numeric(28,10),
    unit_of_measure character varying(100),
    unit_price numeric(28,10),
    effective_price numeric(28,10),
    resource_id text,
    resource_key text NOT NULL,
    resource_name character varying(400),
    resource_group character varying(200),
    resource_type character varying(300),
    service_name character varying(200),
    service_family character varying(200),
    consumed_service character varying(200),
    meter_id character varying(100),
    meter_name character varying(300),
    meter_category character varying(200),
    meter_subcategory character varying(300),
    meter_region character varying(100),
    product_name character varying(400),
    sku character varying(200),
    frequency character varying(64),
    benefit_id character varying(300),
    benefit_name character varying(300),
    publisher_type character varying(64),
    source_cost_center character varying(200),
    tags jsonb,
    additional_info jsonb,
    extra jsonb,
    project character varying(200),
    team character varying(200),
    business_unit character varying(200),
    workload character varying(200),
    attribution_source character varying(200),
    normalizer_version character varying(32) NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: cost_records_staging; Type: TABLE; Schema: public; Owner: -
--

CREATE UNLOGGED TABLE public.cost_records_staging (
    usage_date date NOT NULL,
    export_run_id bigint,
    ingestion_file_id bigint,
    source_row_number integer,
    billing_period_start date,
    billing_period_end date,
    cost numeric(28,10) NOT NULL,
    cost_usd numeric(28,10),
    payg_cost numeric(28,10),
    quantity numeric(28,10),
    unit_of_measure character varying(100),
    unit_price numeric(28,10),
    effective_price numeric(28,10),
    resource_id text,
    resource_key text NOT NULL,
    resource_name character varying(400),
    resource_group character varying(200),
    resource_type character varying(300),
    service_name character varying(200),
    service_family character varying(200),
    consumed_service character varying(200),
    meter_id character varying(100),
    meter_name character varying(300),
    meter_category character varying(200),
    meter_subcategory character varying(300),
    meter_region character varying(100),
    product_name character varying(400),
    sku character varying(200),
    frequency character varying(64),
    benefit_id character varying(300),
    benefit_name character varying(300),
    publisher_type character varying(64),
    source_cost_center character varying(200),
    tags jsonb,
    additional_info jsonb,
    extra jsonb,
    project character varying(200),
    team character varying(200),
    business_unit character varying(200),
    workload character varying(200),
    attribution_source character varying(200),
    normalizer_version character varying(32) NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: daily_cost_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_cost_aggregates (
    id bigint NOT NULL,
    usage_date date NOT NULL,
    cost numeric(28,10) NOT NULL,
    record_count integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: daily_cost_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.daily_cost_aggregates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: daily_cost_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.daily_cost_aggregates_id_seq OWNED BY public.daily_cost_aggregates.id;


--
-- Name: environments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.environments (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(100) NOT NULL,
    environment_group character varying(32) NOT NULL,
    is_production boolean NOT NULL,
    sort_order integer NOT NULL,
    description text
);


--
-- Name: environments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.environments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: environments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.environments_id_seq OWNED BY public.environments.id;


--
-- Name: export_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.export_definitions (
    id integer NOT NULL,
    subscription_fk integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    export_name character varying(200) NOT NULL,
    storage_account_url character varying(500),
    container character varying(200) NOT NULL,
    root_folder_path character varying(500) NOT NULL,
    file_format character varying(16) NOT NULL,
    enabled boolean NOT NULL,
    last_discovery_at timestamp with time zone,
    last_discovery_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: export_definitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.export_definitions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: export_definitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.export_definitions_id_seq OWNED BY public.export_definitions.id;


--
-- Name: export_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.export_runs (
    id bigint NOT NULL,
    export_definition_id integer NOT NULL,
    subscription_fk integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    run_key character varying(700) NOT NULL,
    period_start date,
    period_end date,
    submitted_at timestamp with time zone,
    manifest jsonb,
    status character varying(32) NOT NULL,
    file_count integer NOT NULL,
    row_count integer,
    rows_rejected integer,
    total_cost numeric(28,10),
    days_applied integer,
    days_skipped_newer integer,
    applied_at timestamp with time zone,
    job_id bigint,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: export_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.export_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: export_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.export_runs_id_seq OWNED BY public.export_runs.id;


--
-- Name: forecast_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.forecast_records (
    id bigint NOT NULL,
    generated_on date NOT NULL,
    as_of_date date NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_ref character varying(200),
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    method character varying(64) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    actual_to_date numeric(28,10) NOT NULL,
    forecast_total numeric(28,10) NOT NULL,
    details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: forecast_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.forecast_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: forecast_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.forecast_records_id_seq OWNED BY public.forecast_records.id;


--
-- Name: ingestion_audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_audit_logs (
    id bigint NOT NULL,
    job_id bigint,
    subscription_fk integer,
    operation character varying(100) NOT NULL,
    level character varying(16) NOT NULL,
    message text NOT NULL,
    details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ingestion_audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_audit_logs_id_seq OWNED BY public.ingestion_audit_logs.id;


--
-- Name: ingestion_errors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_errors (
    id bigint NOT NULL,
    job_id bigint,
    export_run_id bigint,
    ingestion_file_id bigint,
    subscription_fk integer,
    row_number integer,
    error_type character varying(64) NOT NULL,
    message text NOT NULL,
    raw jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ingestion_errors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_errors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_errors_id_seq OWNED BY public.ingestion_errors.id;


--
-- Name: ingestion_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_files (
    id bigint NOT NULL,
    export_run_id bigint,
    export_definition_id integer NOT NULL,
    subscription_fk integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    blob_path text NOT NULL,
    size_bytes bigint,
    content_hash character varying(64) NOT NULL,
    etag character varying(200),
    last_modified timestamp with time zone,
    status character varying(32) NOT NULL,
    rows_read integer,
    rows_loaded integer,
    rows_rejected integer,
    cost_total numeric(28,10),
    detected_schema character varying(64),
    source_columns jsonb,
    schema_mapping jsonb,
    normalizer_version character varying(32),
    processed_at timestamp with time zone,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ingestion_files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_files_id_seq OWNED BY public.ingestion_files.id;


--
-- Name: ingestion_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_jobs (
    id bigint NOT NULL,
    job_type character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    subscription_fk integer,
    dataset_type character varying(32),
    params jsonb NOT NULL,
    priority integer NOT NULL,
    attempts integer NOT NULL,
    max_attempts integer NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    locked_by character varying(200),
    locked_at timestamp with time zone,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    progress jsonb,
    result jsonb,
    error_message text,
    error_details jsonb,
    triggered_by character varying(200) NOT NULL,
    parent_job_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ingestion_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_jobs_id_seq OWNED BY public.ingestion_jobs.id;


--
-- Name: meter_cost_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.meter_cost_aggregates (
    id bigint NOT NULL,
    usage_date date NOT NULL,
    resource_key text NOT NULL,
    resource_name character varying(400),
    resource_group character varying(200),
    resource_type character varying(300),
    meter_id character varying(100),
    meter_category character varying(200),
    meter_subcategory character varying(300),
    meter_name character varying(300),
    unit_of_measure character varying(100),
    sku character varying(200),
    cost numeric(28,10) NOT NULL,
    quantity numeric(28,10),
    record_count integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: meter_cost_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.meter_cost_aggregates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: meter_cost_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.meter_cost_aggregates_id_seq OWNED BY public.meter_cost_aggregates.id;


--
-- Name: monthly_cost_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monthly_cost_aggregates (
    id bigint NOT NULL,
    usage_date date NOT NULL,
    cost numeric(28,10) NOT NULL,
    record_count integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: monthly_cost_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.monthly_cost_aggregates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: monthly_cost_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.monthly_cost_aggregates_id_seq OWNED BY public.monthly_cost_aggregates.id;


--
-- Name: notification_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_history (
    id bigint NOT NULL,
    alert_rule_id integer,
    notification_type character varying(64) NOT NULL,
    severity character varying(32) NOT NULL,
    title character varying(400) NOT NULL,
    message text NOT NULL,
    link character varying(500),
    entity_type character varying(64),
    entity_id character varying(200),
    dedup_key character varying(400) NOT NULL,
    channel character varying(32) NOT NULL,
    delivery_status character varying(32) NOT NULL,
    is_read boolean NOT NULL,
    read_at timestamp with time zone,
    read_by character varying(200),
    is_demo boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notification_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notification_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notification_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_history_id_seq OWNED BY public.notification_history.id;


--
-- Name: resource_cost_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_cost_aggregates (
    id bigint NOT NULL,
    usage_date date NOT NULL,
    resource_key text NOT NULL,
    resource_name character varying(400),
    resource_group character varying(200),
    resource_type character varying(300),
    tags jsonb,
    cost numeric(28,10) NOT NULL,
    record_count integer NOT NULL,
    dataset_type character varying(32) NOT NULL,
    billing_currency character varying(3) NOT NULL,
    subscription_fk integer NOT NULL,
    application_id integer,
    environment_id integer,
    allocation_status character varying(32) NOT NULL,
    service_category character varying(100) NOT NULL,
    region character varying(100),
    charge_type character varying(64),
    pricing_model character varying(64),
    owner character varying(200),
    cost_center character varying(200),
    is_demo boolean NOT NULL
);


--
-- Name: resource_cost_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_cost_aggregates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_cost_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_cost_aggregates_id_seq OWNED BY public.resource_cost_aggregates.id;


--
-- Name: resource_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_groups (
    id integer NOT NULL,
    subscription_fk integer NOT NULL,
    name character varying(200) NOT NULL,
    display_name character varying(200) NOT NULL,
    first_seen_date date,
    last_seen_date date
);


--
-- Name: resource_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_groups_id_seq OWNED BY public.resource_groups.id;


--
-- Name: resource_tag_mappings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_tag_mappings (
    id integer NOT NULL,
    tag_key character varying(200) NOT NULL,
    tag_value character varying(400),
    target_dimension character varying(64) NOT NULL,
    target_value character varying(400),
    priority integer NOT NULL,
    enabled boolean NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: resource_tag_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_tag_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_tag_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_tag_mappings_id_seq OWNED BY public.resource_tag_mappings.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    entra_app_role character varying(100)
);


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: savings_opportunities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.savings_opportunities (
    id bigint NOT NULL,
    opportunity_key character varying(500) NOT NULL,
    rule_code character varying(64) NOT NULL,
    title character varying(400) NOT NULL,
    resource_key text,
    resource_name character varying(400),
    subscription_fk integer,
    application_id integer,
    environment_id integer,
    service_category character varying(100),
    billing_currency character varying(3) NOT NULL,
    current_monthly_cost numeric(28,10) NOT NULL,
    estimated_monthly_savings numeric(28,10),
    savings_basis text,
    issue text NOT NULL,
    evidence jsonb NOT NULL,
    recommendation text NOT NULL,
    evidence_source character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    detected_at timestamp with time zone DEFAULT now() NOT NULL,
    last_evaluated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_demo boolean NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: savings_opportunities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.savings_opportunities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: savings_opportunities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.savings_opportunities_id_seq OWNED BY public.savings_opportunities.id;


--
-- Name: service_category_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_category_rules (
    id integer NOT NULL,
    match_field character varying(64) NOT NULL,
    pattern character varying(300) NOT NULL,
    category character varying(100) NOT NULL,
    priority integer NOT NULL,
    enabled boolean NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: service_category_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_category_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_category_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_category_rules_id_seq OWNED BY public.service_category_rules.id;


--
-- Name: service_cost_aggregates; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.service_cost_aggregates AS
 SELECT usage_date AS month_start,
    dataset_type,
    billing_currency,
    subscription_fk,
    application_id,
    environment_id,
    allocation_status,
    service_category,
    sum(cost) AS cost
   FROM public.monthly_cost_aggregates
  GROUP BY usage_date, dataset_type, billing_currency, subscription_fk, application_id, environment_id, allocation_status, service_category;


--
-- Name: user_role_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_role_assignments (
    id integer NOT NULL,
    user_id integer NOT NULL,
    role_id integer NOT NULL,
    application_id integer,
    created_by character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_role_assignments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_role_assignments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_role_assignments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_role_assignments_id_seq OWNED BY public.user_role_assignments.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    external_id character varying(200) NOT NULL,
    email character varying(320),
    display_name character varying(200),
    is_active boolean NOT NULL,
    last_login_at timestamp with time zone,
    preferences jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: weekly_cost_aggregates; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.weekly_cost_aggregates AS
 SELECT (d.usage_date - ((((EXTRACT(isodow FROM d.usage_date))::integer - ws.dow) + 7) % 7)) AS week_start,
    d.dataset_type,
    d.billing_currency,
    d.subscription_fk,
    d.application_id,
    d.environment_id,
    d.allocation_status,
    d.service_category,
    d.region,
    d.charge_type,
    d.pricing_model,
    d.owner,
    d.cost_center,
    d.is_demo,
    sum(d.cost) AS cost,
    sum(d.record_count) AS record_count
   FROM (public.daily_cost_aggregates d
     CROSS JOIN ( SELECT COALESCE(( SELECT ((application_settings.value #>> '{}'::text[]))::integer AS int4
                   FROM public.application_settings
                  WHERE ((application_settings.key)::text = 'reporting.week_start_isodow'::text)), 1) AS dow) ws)
  GROUP BY (d.usage_date - ((((EXTRACT(isodow FROM d.usage_date))::integer - ws.dow) + 7) % 7)), d.dataset_type, d.billing_currency, d.subscription_fk, d.application_id, d.environment_id, d.allocation_status, d.service_category, d.region, d.charge_type, d.pricing_model, d.owner, d.cost_center, d.is_demo;


--
-- Name: cost_records_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records ATTACH PARTITION public.cost_records_default DEFAULT;


--
-- Name: alert_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_rules ALTER COLUMN id SET DEFAULT nextval('public.alert_rules_id_seq'::regclass);


--
-- Name: anomaly_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_events ALTER COLUMN id SET DEFAULT nextval('public.anomaly_events_id_seq'::regclass);


--
-- Name: anomaly_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_rules ALTER COLUMN id SET DEFAULT nextval('public.anomaly_rules_id_seq'::regclass);


--
-- Name: application_mappings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_mappings ALTER COLUMN id SET DEFAULT nextval('public.application_mappings_id_seq'::regclass);


--
-- Name: applications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications ALTER COLUMN id SET DEFAULT nextval('public.applications_id_seq'::regclass);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: azure_resources id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_resources ALTER COLUMN id SET DEFAULT nextval('public.azure_resources_id_seq'::regclass);


--
-- Name: azure_subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.azure_subscriptions_id_seq'::regclass);


--
-- Name: budgets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.budgets ALTER COLUMN id SET DEFAULT nextval('public.budgets_id_seq'::regclass);


--
-- Name: cost_anomalies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_anomalies ALTER COLUMN id SET DEFAULT nextval('public.cost_anomalies_id_seq'::regclass);


--
-- Name: cost_comparisons id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_comparisons ALTER COLUMN id SET DEFAULT nextval('public.cost_comparisons_id_seq'::regclass);


--
-- Name: cost_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records ALTER COLUMN id SET DEFAULT nextval('public.cost_records_id_seq'::regclass);


--
-- Name: daily_cost_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_cost_aggregates ALTER COLUMN id SET DEFAULT nextval('public.daily_cost_aggregates_id_seq'::regclass);


--
-- Name: environments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.environments ALTER COLUMN id SET DEFAULT nextval('public.environments_id_seq'::regclass);


--
-- Name: export_definitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_definitions ALTER COLUMN id SET DEFAULT nextval('public.export_definitions_id_seq'::regclass);


--
-- Name: export_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_runs ALTER COLUMN id SET DEFAULT nextval('public.export_runs_id_seq'::regclass);


--
-- Name: forecast_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forecast_records ALTER COLUMN id SET DEFAULT nextval('public.forecast_records_id_seq'::regclass);


--
-- Name: ingestion_audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_audit_logs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_audit_logs_id_seq'::regclass);


--
-- Name: ingestion_errors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_errors ALTER COLUMN id SET DEFAULT nextval('public.ingestion_errors_id_seq'::regclass);


--
-- Name: ingestion_files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files ALTER COLUMN id SET DEFAULT nextval('public.ingestion_files_id_seq'::regclass);


--
-- Name: ingestion_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_jobs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_jobs_id_seq'::regclass);


--
-- Name: meter_cost_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meter_cost_aggregates ALTER COLUMN id SET DEFAULT nextval('public.meter_cost_aggregates_id_seq'::regclass);


--
-- Name: monthly_cost_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_cost_aggregates ALTER COLUMN id SET DEFAULT nextval('public.monthly_cost_aggregates_id_seq'::regclass);


--
-- Name: notification_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_history ALTER COLUMN id SET DEFAULT nextval('public.notification_history_id_seq'::regclass);


--
-- Name: resource_cost_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_cost_aggregates ALTER COLUMN id SET DEFAULT nextval('public.resource_cost_aggregates_id_seq'::regclass);


--
-- Name: resource_groups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_groups ALTER COLUMN id SET DEFAULT nextval('public.resource_groups_id_seq'::regclass);


--
-- Name: resource_tag_mappings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_tag_mappings ALTER COLUMN id SET DEFAULT nextval('public.resource_tag_mappings_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: savings_opportunities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_opportunities ALTER COLUMN id SET DEFAULT nextval('public.savings_opportunities_id_seq'::regclass);


--
-- Name: service_category_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_category_rules ALTER COLUMN id SET DEFAULT nextval('public.service_category_rules_id_seq'::regclass);


--
-- Name: user_role_assignments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments ALTER COLUMN id SET DEFAULT nextval('public.user_role_assignments_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: cost_records pk_cost_records; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records
    ADD CONSTRAINT pk_cost_records PRIMARY KEY (id, usage_date);


--
-- Name: cost_records_default cost_records_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_records_default
    ADD CONSTRAINT cost_records_default_pkey PRIMARY KEY (id, usage_date);


--
-- Name: alert_rules pk_alert_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_rules
    ADD CONSTRAINT pk_alert_rules PRIMARY KEY (id);


--
-- Name: anomaly_events pk_anomaly_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_events
    ADD CONSTRAINT pk_anomaly_events PRIMARY KEY (id);


--
-- Name: anomaly_rules pk_anomaly_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_rules
    ADD CONSTRAINT pk_anomaly_rules PRIMARY KEY (id);


--
-- Name: application_mappings pk_application_mappings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_mappings
    ADD CONSTRAINT pk_application_mappings PRIMARY KEY (id);


--
-- Name: application_settings pk_application_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_settings
    ADD CONSTRAINT pk_application_settings PRIMARY KEY (key);


--
-- Name: applications pk_applications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT pk_applications PRIMARY KEY (id);


--
-- Name: audit_logs pk_audit_logs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT pk_audit_logs PRIMARY KEY (id);


--
-- Name: azure_resources pk_azure_resources; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_resources
    ADD CONSTRAINT pk_azure_resources PRIMARY KEY (id);


--
-- Name: azure_subscriptions pk_azure_subscriptions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_subscriptions
    ADD CONSTRAINT pk_azure_subscriptions PRIMARY KEY (id);


--
-- Name: budgets pk_budgets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.budgets
    ADD CONSTRAINT pk_budgets PRIMARY KEY (id);


--
-- Name: cost_anomalies pk_cost_anomalies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_anomalies
    ADD CONSTRAINT pk_cost_anomalies PRIMARY KEY (id);


--
-- Name: cost_comparisons pk_cost_comparisons; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_comparisons
    ADD CONSTRAINT pk_cost_comparisons PRIMARY KEY (id);


--
-- Name: cost_data_slices pk_cost_data_slices; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_data_slices
    ADD CONSTRAINT pk_cost_data_slices PRIMARY KEY (subscription_fk, dataset_type, usage_date);


--
-- Name: daily_cost_aggregates pk_daily_cost_aggregates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_cost_aggregates
    ADD CONSTRAINT pk_daily_cost_aggregates PRIMARY KEY (id);


--
-- Name: environments pk_environments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.environments
    ADD CONSTRAINT pk_environments PRIMARY KEY (id);


--
-- Name: export_definitions pk_export_definitions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_definitions
    ADD CONSTRAINT pk_export_definitions PRIMARY KEY (id);


--
-- Name: export_runs pk_export_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_runs
    ADD CONSTRAINT pk_export_runs PRIMARY KEY (id);


--
-- Name: forecast_records pk_forecast_records; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forecast_records
    ADD CONSTRAINT pk_forecast_records PRIMARY KEY (id);


--
-- Name: ingestion_audit_logs pk_ingestion_audit_logs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_audit_logs
    ADD CONSTRAINT pk_ingestion_audit_logs PRIMARY KEY (id);


--
-- Name: ingestion_errors pk_ingestion_errors; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_errors
    ADD CONSTRAINT pk_ingestion_errors PRIMARY KEY (id);


--
-- Name: ingestion_files pk_ingestion_files; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files
    ADD CONSTRAINT pk_ingestion_files PRIMARY KEY (id);


--
-- Name: ingestion_jobs pk_ingestion_jobs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_jobs
    ADD CONSTRAINT pk_ingestion_jobs PRIMARY KEY (id);


--
-- Name: meter_cost_aggregates pk_meter_cost_aggregates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meter_cost_aggregates
    ADD CONSTRAINT pk_meter_cost_aggregates PRIMARY KEY (id);


--
-- Name: monthly_cost_aggregates pk_monthly_cost_aggregates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monthly_cost_aggregates
    ADD CONSTRAINT pk_monthly_cost_aggregates PRIMARY KEY (id);


--
-- Name: notification_history pk_notification_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_history
    ADD CONSTRAINT pk_notification_history PRIMARY KEY (id);


--
-- Name: resource_cost_aggregates pk_resource_cost_aggregates; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_cost_aggregates
    ADD CONSTRAINT pk_resource_cost_aggregates PRIMARY KEY (id);


--
-- Name: resource_groups pk_resource_groups; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_groups
    ADD CONSTRAINT pk_resource_groups PRIMARY KEY (id);


--
-- Name: resource_tag_mappings pk_resource_tag_mappings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_tag_mappings
    ADD CONSTRAINT pk_resource_tag_mappings PRIMARY KEY (id);


--
-- Name: roles pk_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT pk_roles PRIMARY KEY (id);


--
-- Name: savings_opportunities pk_savings_opportunities; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_opportunities
    ADD CONSTRAINT pk_savings_opportunities PRIMARY KEY (id);


--
-- Name: service_category_rules pk_service_category_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_category_rules
    ADD CONSTRAINT pk_service_category_rules PRIMARY KEY (id);


--
-- Name: user_role_assignments pk_user_role_assignments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments
    ADD CONSTRAINT pk_user_role_assignments PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: anomaly_rules uq_anomaly_rules_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_rules
    ADD CONSTRAINT uq_anomaly_rules_code UNIQUE (code);


--
-- Name: applications uq_applications_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT uq_applications_code UNIQUE (code);


--
-- Name: azure_resources uq_azure_resources_resource_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_resources
    ADD CONSTRAINT uq_azure_resources_resource_key UNIQUE (resource_key);


--
-- Name: azure_subscriptions uq_azure_subscriptions_subscription_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_subscriptions
    ADD CONSTRAINT uq_azure_subscriptions_subscription_id UNIQUE (subscription_id);


--
-- Name: environments uq_environments_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.environments
    ADD CONSTRAINT uq_environments_code UNIQUE (code);


--
-- Name: export_definitions uq_export_definitions_subscription_fk_dataset_type_export_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_definitions
    ADD CONSTRAINT uq_export_definitions_subscription_fk_dataset_type_export_name UNIQUE (subscription_fk, dataset_type, export_name);


--
-- Name: export_runs uq_export_runs_export_definition_id_run_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_runs
    ADD CONSTRAINT uq_export_runs_export_definition_id_run_key UNIQUE (export_definition_id, run_key);


--
-- Name: ingestion_files uq_ingestion_files_export_definition_id_blob_path_content_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files
    ADD CONSTRAINT uq_ingestion_files_export_definition_id_blob_path_content_hash UNIQUE (export_definition_id, blob_path, content_hash);


--
-- Name: notification_history uq_notification_history_dedup_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_history
    ADD CONSTRAINT uq_notification_history_dedup_key UNIQUE (dedup_key);


--
-- Name: resource_groups uq_resource_groups_subscription_fk_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_groups
    ADD CONSTRAINT uq_resource_groups_subscription_fk_name UNIQUE (subscription_fk, name);


--
-- Name: roles uq_roles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_code UNIQUE (code);


--
-- Name: savings_opportunities uq_savings_opportunities_opportunity_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_opportunities
    ADD CONSTRAINT uq_savings_opportunities_opportunity_key UNIQUE (opportunity_key);


--
-- Name: user_role_assignments uq_user_role_assignments_user_id_role_id_application_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments
    ADD CONSTRAINT uq_user_role_assignments_user_id_role_id_application_id UNIQUE (user_id, role_id, application_id);


--
-- Name: users uq_users_external_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_external_id UNIQUE (external_id);


--
-- Name: ix_cost_records_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_records_run ON ONLY public.cost_records USING btree (export_run_id);


--
-- Name: cost_records_default_export_run_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cost_records_default_export_run_id_idx ON public.cost_records_default USING btree (export_run_id);


--
-- Name: ix_cost_records_file; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_records_file ON ONLY public.cost_records USING btree (ingestion_file_id);


--
-- Name: cost_records_default_ingestion_file_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cost_records_default_ingestion_file_id_idx ON public.cost_records_default USING btree (ingestion_file_id);


--
-- Name: ix_cost_records_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_records_resource ON ONLY public.cost_records USING btree (resource_key, dataset_type, usage_date);


--
-- Name: cost_records_default_resource_key_dataset_type_usage_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cost_records_default_resource_key_dataset_type_usage_date_idx ON public.cost_records_default USING btree (resource_key, dataset_type, usage_date);


--
-- Name: ix_cost_records_slice; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_records_slice ON ONLY public.cost_records USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: cost_records_default_subscription_fk_dataset_type_usage_dat_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cost_records_default_subscription_fk_dataset_type_usage_dat_idx ON public.cost_records_default USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: ix_anomaly_events_anomaly; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_anomaly_events_anomaly ON public.anomaly_events USING btree (anomaly_id, created_at);


--
-- Name: ix_audit_logs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created ON public.audit_logs USING btree (created_at);


--
-- Name: ix_cost_anomalies_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_anomalies_resource ON public.cost_anomalies USING btree (resource_key);


--
-- Name: ix_cost_anomalies_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_anomalies_scope ON public.cost_anomalies USING btree (rule_code, scope_key, last_detected_date);


--
-- Name: ix_cost_anomalies_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_anomalies_status ON public.cost_anomalies USING btree (status, detection_date);


--
-- Name: ix_cost_records_staging_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cost_records_staging_run ON public.cost_records_staging USING btree (export_run_id, usage_date);


--
-- Name: ix_dca_main; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dca_main ON public.daily_cost_aggregates USING btree (dataset_type, billing_currency, usage_date);


--
-- Name: ix_dca_sub_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dca_sub_date ON public.daily_cost_aggregates USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: ix_forecast_records_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_forecast_records_scope ON public.forecast_records USING btree (scope_type, scope_ref, generated_on);


--
-- Name: ix_ingestion_audit_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_audit_created ON public.ingestion_audit_logs USING btree (created_at);


--
-- Name: ix_ingestion_errors_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_errors_job ON public.ingestion_errors USING btree (job_id);


--
-- Name: ix_ingestion_files_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_files_hash ON public.ingestion_files USING btree (export_definition_id, content_hash);


--
-- Name: ix_ingestion_jobs_queue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_jobs_queue ON public.ingestion_jobs USING btree (status, next_attempt_at, priority);


--
-- Name: ix_ingestion_jobs_sub; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ingestion_jobs_sub ON public.ingestion_jobs USING btree (subscription_fk, created_at);


--
-- Name: ix_mca_main; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mca_main ON public.monthly_cost_aggregates USING btree (dataset_type, billing_currency, usage_date);


--
-- Name: ix_mca_sub_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mca_sub_date ON public.monthly_cost_aggregates USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: ix_mtca_main; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mtca_main ON public.meter_cost_aggregates USING btree (dataset_type, billing_currency, usage_date);


--
-- Name: ix_mtca_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mtca_resource ON public.meter_cost_aggregates USING btree (resource_key, dataset_type, usage_date);


--
-- Name: ix_mtca_sub_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mtca_sub_date ON public.meter_cost_aggregates USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: ix_notification_history_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notification_history_created ON public.notification_history USING btree (created_at);


--
-- Name: ix_rca_main; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rca_main ON public.resource_cost_aggregates USING btree (dataset_type, billing_currency, usage_date);


--
-- Name: ix_rca_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rca_resource ON public.resource_cost_aggregates USING btree (resource_key, dataset_type, usage_date);


--
-- Name: ix_rca_sub_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rca_sub_date ON public.resource_cost_aggregates USING btree (subscription_fk, dataset_type, usage_date);


--
-- Name: ix_savings_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_savings_status ON public.savings_opportunities USING btree (status);


--
-- Name: cost_records_default_export_run_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_cost_records_run ATTACH PARTITION public.cost_records_default_export_run_id_idx;


--
-- Name: cost_records_default_ingestion_file_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_cost_records_file ATTACH PARTITION public.cost_records_default_ingestion_file_id_idx;


--
-- Name: cost_records_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.pk_cost_records ATTACH PARTITION public.cost_records_default_pkey;


--
-- Name: cost_records_default_resource_key_dataset_type_usage_date_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_cost_records_resource ATTACH PARTITION public.cost_records_default_resource_key_dataset_type_usage_date_idx;


--
-- Name: cost_records_default_subscription_fk_dataset_type_usage_dat_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.ix_cost_records_slice ATTACH PARTITION public.cost_records_default_subscription_fk_dataset_type_usage_dat_idx;


--
-- Name: anomaly_events fk_anomaly_events_anomaly_id_cost_anomalies; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.anomaly_events
    ADD CONSTRAINT fk_anomaly_events_anomaly_id_cost_anomalies FOREIGN KEY (anomaly_id) REFERENCES public.cost_anomalies(id) ON DELETE CASCADE;


--
-- Name: application_mappings fk_application_mappings_application_id_applications; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_mappings
    ADD CONSTRAINT fk_application_mappings_application_id_applications FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;


--
-- Name: application_mappings fk_application_mappings_environment_id_environments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_mappings
    ADD CONSTRAINT fk_application_mappings_environment_id_environments FOREIGN KEY (environment_id) REFERENCES public.environments(id) ON DELETE SET NULL;


--
-- Name: application_mappings fk_application_mappings_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_mappings
    ADD CONSTRAINT fk_application_mappings_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: azure_resources fk_azure_resources_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_resources
    ADD CONSTRAINT fk_azure_resources_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: azure_subscriptions fk_azure_subscriptions_application_id_applications; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_subscriptions
    ADD CONSTRAINT fk_azure_subscriptions_application_id_applications FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE SET NULL;


--
-- Name: azure_subscriptions fk_azure_subscriptions_environment_id_environments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.azure_subscriptions
    ADD CONSTRAINT fk_azure_subscriptions_environment_id_environments FOREIGN KEY (environment_id) REFERENCES public.environments(id) ON DELETE SET NULL;


--
-- Name: cost_anomalies fk_cost_anomalies_rule_id_anomaly_rules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_anomalies
    ADD CONSTRAINT fk_cost_anomalies_rule_id_anomaly_rules FOREIGN KEY (rule_id) REFERENCES public.anomaly_rules(id) ON DELETE SET NULL;


--
-- Name: export_definitions fk_export_definitions_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_definitions
    ADD CONSTRAINT fk_export_definitions_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: export_runs fk_export_runs_export_definition_id_export_definitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_runs
    ADD CONSTRAINT fk_export_runs_export_definition_id_export_definitions FOREIGN KEY (export_definition_id) REFERENCES public.export_definitions(id) ON DELETE CASCADE;


--
-- Name: export_runs fk_export_runs_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.export_runs
    ADD CONSTRAINT fk_export_runs_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: ingestion_files fk_ingestion_files_export_definition_id_export_definitions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files
    ADD CONSTRAINT fk_ingestion_files_export_definition_id_export_definitions FOREIGN KEY (export_definition_id) REFERENCES public.export_definitions(id) ON DELETE CASCADE;


--
-- Name: ingestion_files fk_ingestion_files_export_run_id_export_runs; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files
    ADD CONSTRAINT fk_ingestion_files_export_run_id_export_runs FOREIGN KEY (export_run_id) REFERENCES public.export_runs(id) ON DELETE SET NULL;


--
-- Name: ingestion_files fk_ingestion_files_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_files
    ADD CONSTRAINT fk_ingestion_files_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: ingestion_jobs fk_ingestion_jobs_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_jobs
    ADD CONSTRAINT fk_ingestion_jobs_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE SET NULL;


--
-- Name: notification_history fk_notification_history_alert_rule_id_alert_rules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_history
    ADD CONSTRAINT fk_notification_history_alert_rule_id_alert_rules FOREIGN KEY (alert_rule_id) REFERENCES public.alert_rules(id) ON DELETE SET NULL;


--
-- Name: resource_groups fk_resource_groups_subscription_fk_azure_subscriptions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_groups
    ADD CONSTRAINT fk_resource_groups_subscription_fk_azure_subscriptions FOREIGN KEY (subscription_fk) REFERENCES public.azure_subscriptions(id) ON DELETE CASCADE;


--
-- Name: user_role_assignments fk_user_role_assignments_application_id_applications; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments
    ADD CONSTRAINT fk_user_role_assignments_application_id_applications FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;


--
-- Name: user_role_assignments fk_user_role_assignments_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments
    ADD CONSTRAINT fk_user_role_assignments_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: user_role_assignments fk_user_role_assignments_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role_assignments
    ADD CONSTRAINT fk_user_role_assignments_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict tzkkyNRhy9t1morrNf0R2AY7dSwuHqGBYeC7IwGzKkrMqcvS9Susj4sL9Doaee0

