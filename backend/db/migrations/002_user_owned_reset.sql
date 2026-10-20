-- Remove the retired ownership model. Existing organization-owned content is
-- deliberately discarded; no data is assigned or converted to a user.
DELETE FROM platform_documents
WHERE left(collection, length('adk_memory_events_')) = 'adk_memory_events_'
   OR collection IN ('tenants', 'tenant_domains', 'tenant_migration_runs', 'tenant_migration_operations', 'clients', 'client_config_cache', 'permission_groups', 'tenant_budget_ledger')
   OR (collection = 'tool_permissions' AND doc_id LIKE 'tenant:%')
   OR (collection NOT IN ('auth_users', 'platform_config', 'mcp_servers')
       AND COALESCE(data->>'tenantId', '') <> '');

DELETE FROM platform_documents
WHERE collection = 'mcp_servers' AND data->>'scope' = 'tenant';

UPDATE platform_documents
SET data = data - 'tenantId' - 'permissionGroupIds' || jsonb_build_object(
    'groupTags', COALESCE((SELECT jsonb_agg(tag) FROM jsonb_array_elements_text(
        COALESCE(data->'groupTags', '[]'::jsonb)) AS tags(tag) WHERE tag NOT LIKE 'tenant-admin:%'), '[]'::jsonb)),
    updated_at = now()
WHERE collection = 'auth_users';

UPDATE platform_documents
SET data = data #- '{agent,tenantOverrides}', updated_at = now()
WHERE collection = 'platform_config';

UPDATE platform_documents SET data = data - 'scope' - 'tenantId', updated_at = now()
WHERE collection = 'mcp_servers';

-- ADK keeps its own tables. Delete only its retired app namespaces, when those
-- tables/columns exist; fresh databases need no special initialization.
DO $$
DECLARE target_table text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY['events', 'sessions', 'user_states', 'app_states'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns c
                   WHERE c.table_schema = current_schema() AND c.table_name = target_table AND c.column_name = 'app_name') THEN
            EXECUTE format('DELETE FROM %I WHERE app_name LIKE $1', target_table) USING 'tenant-%';
        END IF;
    END LOOP;
END $$;

UPDATE platform_documents SET data = data - 'tenantId', updated_at = now() WHERE data ? 'tenantId';
