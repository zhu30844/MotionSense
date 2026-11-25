#include "motionsense/config.h"
#include "motionsense/utils.h"
#include "log.h"

#include <cjson/cJSON.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifdef LOG_TAG
#undef LOG_TAG
#endif
#define LOG_TAG "config"

ms_config_t g_cfg;

/* ------------------------------------------------------------------ */
/* What is configurable: loading and saving both walk this one list   */
/* ------------------------------------------------------------------ */
typedef enum { T_INT, T_U32, T_DOUBLE, T_BOOL, T_OSD_POS } field_type_t;

typedef struct {
    const char  *section;
    const char  *key;
    field_type_t type;
    void        *value;
} field_t;

#define F(sec, key, type) { #sec, #key, type, &g_cfg.sec.key }

static const field_t s_fields[] = {
    F(h264, width,        T_U32),
    F(h264, height,       T_U32),
    F(h264, fps,          T_INT),
    F(h264, bitrate_kbps, T_U32),
    F(h264, gop,          T_INT),

    F(live, width,        T_U32),
    F(live, height,       T_U32),
    F(live, fps,          T_INT),
    F(live, bitrate_kbps, T_U32),
    F(live, gop,          T_INT),

    F(ivs, width,              T_U32),
    F(ivs, height,             T_U32),
    F(ivs, fps,                T_INT),
    F(ivs, md_interval,        T_INT),
    F(ivs, md_sensibility,     T_INT),
    F(ivs, md_night_mode,      T_BOOL),
    F(ivs, thresh_sad,         T_INT),
    F(ivs, thresh_move,        T_INT),
    F(ivs, area_ratio,         T_DOUBLE),
    F(ivs, poll_ms,            T_INT),
    F(ivs, fps_low,            T_INT),
    F(ivs, fps_high,           T_INT),
    F(ivs, motion_debounce_ms, T_INT),

    F(osd, font_size, T_INT),
    F(osd, margin,    T_INT),
    F(osd, position,  T_OSD_POS),

    F(storage, hls_duration_s,   T_INT),
    F(storage, disk_free_min_mb, T_U32),
    F(storage, cleanup_every_ts, T_INT),
};

#define FIELD_COUNT (sizeof(s_fields) / sizeof(s_fields[0]))

static const char *const s_osd_pos[] = {
    [OSD_POS_TOP_LEFT]     = "top-left",
    [OSD_POS_TOP_RIGHT]    = "top-right",
    [OSD_POS_BOTTOM_LEFT]  = "bottom-left",
    [OSD_POS_BOTTOM_RIGHT] = "bottom-right",
};

#define OSD_POS_COUNT (sizeof(s_osd_pos) / sizeof(s_osd_pos[0]))

/* ------------------------------------------------------------------ */
/* Defaults                                                            */
/* ------------------------------------------------------------------ */
static void config_defaults(ms_config_t *c)
{
    memset(c, 0, sizeof(*c));

    c->h264.width        = CFG_VI_W;
    c->h264.height       = CFG_VI_H;
    c->h264.fps          = CFG_VI_BASE_FPS;
    c->h264.bitrate_kbps = CFG_H264_BITRATE;
    c->h264.gop          = CFG_FPS_HIGH * 2;

    c->live.width        = CFG_VI_W;
    c->live.height       = CFG_VI_H;
    c->live.fps          = CFG_LIVE_FPS;
    c->live.bitrate_kbps = CFG_LIVE_BITRATE;
    c->live.gop          = CFG_LIVE_FPS;

    c->ivs.width         = CFG_IVS_W;
    c->ivs.height        = CFG_IVS_H;
    c->ivs.fps           = 15;
    c->ivs.md_interval   = 4;
    c->ivs.md_sensibility= 3;
    c->ivs.md_night_mode = true;
    c->ivs.thresh_sad    = 40;
    c->ivs.thresh_move   = 2;
    c->ivs.area_ratio    = CFG_MD_AREA_RATIO;
    c->ivs.poll_ms       = CFG_IVS_POLL_MS;
    c->ivs.fps_low       = CFG_FPS_LOW;
    c->ivs.fps_high      = CFG_FPS_HIGH;
    c->ivs.motion_debounce_ms = CFG_MOTION_DEBOUNCE_MS;

    c->osd.font_size     = CFG_OSD_FONT_SIZE;
    c->osd.margin        = CFG_OSD_MARGIN;
    c->osd.position      = OSD_POS_BOTTOM_RIGHT;

    c->storage.hls_duration_s   = CFG_HLS_DURATION_S;
    c->storage.disk_free_min_mb = CFG_DISK_FREE_MIN_MB;
    c->storage.cleanup_every_ts = CFG_CLEANUP_EVERY_TS;
}

/* ------------------------------------------------------------------ */
/* Load                                                                */
/* ------------------------------------------------------------------ */
/* False when the value has the wrong type; the field keeps its default. */
static bool field_set(const field_t *f, const cJSON *v)
{
    switch (f->type)
    {
    case T_INT:
        if (!cJSON_IsNumber(v)) return false;
        *(int *)f->value = v->valueint;
        return true;
    case T_U32:
        if (!cJSON_IsNumber(v) || v->valuedouble < 0) return false;
        *(uint32_t *)f->value = (uint32_t)v->valuedouble;
        return true;
    case T_DOUBLE:
        if (!cJSON_IsNumber(v)) return false;
        *(double *)f->value = v->valuedouble;
        return true;
    case T_BOOL:
        if (!cJSON_IsBool(v)) return false;
        *(bool *)f->value = cJSON_IsTrue(v);
        return true;
    case T_OSD_POS:
        if (!cJSON_IsString(v)) return false;
        for (size_t i = 0; i < OSD_POS_COUNT; i++)
            if (strcmp(v->valuestring, s_osd_pos[i]) == 0)
            {
                *(osd_position_t *)f->value = (osd_position_t)i;
                return true;
            }
        return false;
    }
    return false;
}

/* ------------------------------------------------------------------ */
/* Save                                                                */
/* ------------------------------------------------------------------ */
static void field_add(const field_t *f, cJSON *section)
{
    switch (f->type)
    {
    case T_INT:     cJSON_AddNumberToObject(section, f->key, *(int *)f->value);      break;
    case T_U32:     cJSON_AddNumberToObject(section, f->key, *(uint32_t *)f->value); break;
    case T_DOUBLE:  cJSON_AddNumberToObject(section, f->key, *(double *)f->value);   break;
    case T_BOOL:    cJSON_AddBoolToObject(section, f->key, *(bool *)f->value);       break;
    case T_OSD_POS: cJSON_AddStringToObject(section, f->key,
                                            s_osd_pos[*(osd_position_t *)f->value]); break;
    }
}

/* Written to a temporary file and renamed, so a failure leaves no half file. */
static int config_save(const char *path)
{
    cJSON *root = cJSON_CreateObject();
    for (size_t i = 0; root && i < FIELD_COUNT; i++)
    {
        const field_t *f = &s_fields[i];
        cJSON *section = cJSON_GetObjectItemCaseSensitive(root, f->section);
        if (!section)
            section = cJSON_AddObjectToObject(root, f->section);
        if (section)
            field_add(f, section);
    }
    char *text = root ? cJSON_Print(root) : NULL;
    cJSON_Delete(root);
    if (!text)
        return -1;

    char tmp[PATH_MAX];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);

    int rc = -1;
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0)
    {
        if (write_all(fd, text, strlen(text)) == 0 &&
            write_all(fd, "\n", 1) == 0 && fsync(fd) == 0)
            rc = 0;
        close(fd);
        if (rc == 0 && rename(tmp, path) != 0)
            rc = -1;
        if (rc == 0)
            fsync_parent_dir(path);
        else
            unlink(tmp);
    }
    free(text);
    return rc;
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */
void ms_config_load(const char *path)
{
    config_defaults(&g_cfg);

    char *text = read_file(path);
    if (!text)
    {
        /* First run: leave the user a file to edit. */
        if (errno == ENOENT && config_save(path) == 0)
            MS_LOG_INFO("no %s, wrote the defaults\n", path);
        else
            MS_LOG_WARN("cannot read %s, using defaults\n", path);
        return;
    }

    cJSON *root = cJSON_Parse(text);
    free(text);
    if (!cJSON_IsObject(root))
    {
        MS_LOG_WARN("%s is not valid JSON, using defaults\n", path);
        cJSON_Delete(root);
        return;
    }

    for (size_t i = 0; i < FIELD_COUNT; i++)
    {
        const field_t *f = &s_fields[i];
        const cJSON *section = cJSON_GetObjectItemCaseSensitive(root, f->section);
        const cJSON *v = cJSON_GetObjectItemCaseSensitive(section, f->key);
        if (v && !field_set(f, v))
            MS_LOG_WARN("%s.%s ignored: wrong type or value\n", f->section, f->key);
    }
    cJSON_Delete(root);

    MS_LOG_INFO("loaded from %s (h264 %ux%u@%d %ukbps, ivs area=%.2f)\n",
             path,
             g_cfg.h264.width, g_cfg.h264.height, g_cfg.h264.fps,
             g_cfg.h264.bitrate_kbps, g_cfg.ivs.area_ratio);
}
