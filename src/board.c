#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <cjson/cJSON.h>

#include "motionsense/board.h"
#include "motionsense/config.h"
#include "motionsense/utils.h"

#include "log.h"

ms_board_t g_board;

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    char *buf = NULL;
    if (fseek(f, 0, SEEK_END) == 0)
    {
        long len = ftell(f);
        rewind(f);
        if (len >= 0 && (buf = malloc((size_t)len + 1)) != NULL)
        {
            size_t got = fread(buf, 1, (size_t)len, f);
            buf[got] = '\0';
        }
    }
    fclose(f);
    return buf;
}

void ms_board_load(void)
{
    ms_board_t *b = &g_board;
    snprintf(b->storage_root, sizeof(b->storage_root), "%s", CFG_STORAGE_ROOT);
    b->storage_removable = true;

    const char *path = getenv("MS_BOARD_FILE");
    if (!path) path = CFG_BOARD_FILE;

    char  *text = read_file(path);
    cJSON *json = text ? cJSON_Parse(text) : NULL;
    if (!json)
        MS_LOG_WARN("%s missing or invalid, using defaults\n", path);

    /* cJSON lookups accept NULL, so a missing object falls through. */
    const cJSON *storage = cJSON_GetObjectItemCaseSensitive(json, "storage");
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(storage, "root");
    if (cJSON_IsString(v) && v->valuestring[0] == '/' &&
        strlen(v->valuestring) < MS_PATH_MAX)
        snprintf(b->storage_root, sizeof(b->storage_root), "%s", v->valuestring);
    else if (v)
        MS_LOG_WARN("storage.root ignored: not an absolute path, or too long\n");
    v = cJSON_GetObjectItemCaseSensitive(storage, "removable");
    if (cJSON_IsBool(v))
        b->storage_removable = cJSON_IsTrue(v);

    cJSON_Delete(json);
    free(text);

    snprintf(b->dcim_root, sizeof(b->dcim_root), "%s/DCIM/", b->storage_root);
    snprintf(b->meta_db, sizeof(b->meta_db), "%sVideoMetadata.db", b->dcim_root);
    snprintf(b->data_dir, sizeof(b->data_dir), "%s/MotionSense", b->storage_root);
    snprintf(b->config_path, sizeof(b->config_path),
             "%s/MotionSense/config.yaml", b->storage_root);

    MS_LOG_INFO("storage %s (%s)\n", b->storage_root,
                b->storage_removable ? "removable" : "fixed");
}

bool ms_storage_present(void)
{
    return !g_board.storage_removable || is_mount_point(g_board.storage_root);
}

int ms_install_path(char *out, size_t size, const char *rel)
{
    char exe[MS_PATH_MAX];
    ssize_t len = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
    if (len <= 0)
        return -1;
    exe[len] = '\0';
    char *slash = strrchr(exe, '/');
    if (!slash)
        return -1;
    *slash = '\0';
    snprintf(out, size, "%s/%s", exe, rel);
    return 0;
}
