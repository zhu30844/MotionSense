/* VI, VENC, IVS and MB: the calls media.c needs behaviour from. */
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "rk_mpi_ivs.h"
#include "rk_mpi_mb.h"
#include "rk_mpi_sys.h"
#include "rk_mpi_venc.h"
#include "rk_mpi_vi.h"

/* The simulated sensor's rate, for a VI channel that sets none. */
#define SENSOR_FPS 30

struct frame { size_t off, len; int key; };
struct clip {
    uint8_t *data;
    struct frame *frm;
    int n, next;
};

struct venc {
    VENC_CHN_ATTR_S attr;
    struct clip clip;
    atomic_bool recv;
    int fps;        /* SetChnParam; 0: every source frame */
    int vi;         /* bound VI channel + 1; 0: fed by SendFrame */
    bool sent;
    uint64_t pts;
    int64_t next;
};

static struct venc s_venc[VENC_MAX_CHN_NUM];
static int s_vi_fps[VI_MAX_CHN_NUM];
static int64_t s_vi_next[VI_MAX_CHN_NUM];

static struct venc *venc_get(VENC_CHN chn)
{
    return chn >= 0 && chn < VENC_MAX_CHN_NUM ? &s_venc[chn] : NULL;
}

static bool vi_valid(VI_CHN chn)
{
    return chn >= 0 && chn < VI_MAX_CHN_NUM;
}

static int vi_fps(VI_CHN chn)
{
    return s_vi_fps[chn] > 0 ? s_vi_fps[chn] : SENSOR_FPS;
}

static int64_t now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
}

static void wait_until(int64_t *next, int64_t period_us)
{
    int64_t now = now_us();
    if (*next < now - period_us)
        *next = now;
    struct timespec ts = { *next / 1000000, (*next % 1000000) * 1000 };
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
    *next += period_us;
}

/* A frame starts at an AUD (H.264) or an SOI (JPEG). */
static bool frame_start(const uint8_t *p, size_t left, bool avc)
{
    if (avc)
        return left >= 5 && !p[0] && !p[1] && !p[2] && p[3] == 1 && (p[4] & 0x1f) == 9;
    return left >= 3 && p[0] == 0xff && p[1] == 0xd8 && p[2] == 0xff;
}

static int clip_load(struct clip *c, const char *name, bool avc)
{
    const char *dir = getenv("PCSIM_SAMPLE_DIR");
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", dir ? dir : PCSIM_SAMPLE_DIR, name);

    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "pcsim: cannot open %s\n", path);
        return -1;
    }
    fseek(f, 0, SEEK_END);
    size_t size = (size_t)ftell(f);
    rewind(f);

    c->data = malloc(size);
    if (!c->data || fread(c->data, 1, size, f) != size) {
        fclose(f);
        return -1;
    }
    fclose(f);

    for (size_t i = 0; i < size; i++) {
        if (!frame_start(c->data + i, size - i, avc))
            continue;
        if (c->n)
            c->frm[c->n - 1].len = i - c->frm[c->n - 1].off;
        struct frame *frm = realloc(c->frm, (size_t)(c->n + 1) * sizeof(*frm));
        if (!frm)
            return -1;
        c->frm = frm;
        c->frm[c->n++] = (struct frame){ .off = i };
    }
    if (!c->n) {
        fprintf(stderr, "pcsim: no frames in %s\n", path);
        return -1;
    }
    c->frm[c->n - 1].len = size - c->frm[c->n - 1].off;

    for (int k = 0; avc && k < c->n; k++) {
        const uint8_t *p = c->data + c->frm[k].off;
        for (size_t i = 0; i + 3 < c->frm[k].len; i++)
            if (!p[i] && !p[i + 1] && p[i + 2] == 1 && (p[i + 3] & 0x1f) == 5)
                c->frm[k].key = 1;
    }
    return 0;
}

static void clip_next(struct venc *v, VENC_STREAM_S *s, uint64_t pts)
{
    struct clip *c = &v->clip;
    struct frame *fr = &c->frm[c->next];
    c->next = (c->next + 1) % c->n;

    VENC_PACK_S *p = s->pstPack;
    memset(p, 0, sizeof(*p));
    p->pMbBlk = c->data + fr->off;
    p->u32Len = (RK_U32)fr->len;
    p->u64PTS = pts;
    p->bFrameEnd = RK_TRUE;
    if (v->attr.stVencAttr.enType == RK_VIDEO_ID_AVC)
        p->DataType.enH264EType = fr->key ? H264E_NALU_IDRSLICE : H264E_NALU_PSLICE;
    s->u32PackCount = 1;
    s->u32Seq++;
}

RK_S32 RK_MPI_VI_SetChnAttr(VI_PIPE ViPipe, VI_CHN ViChn, const VI_CHN_ATTR_S *pstChnAttr)
{
    if (!vi_valid(ViChn))
        return RK_FAILURE;
    s_vi_fps[ViChn] = pstChnAttr->stFrameRate.s32DstFrameRate;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VI_GetChnFrame(VI_PIPE ViPipe, VI_CHN ViChn,
                             VIDEO_FRAME_INFO_S *pstFrameInfo, RK_S32 s32MilliSec)
{
    if (!vi_valid(ViChn))
        return RK_FAILURE;
    wait_until(&s_vi_next[ViChn], 1000000 / vi_fps(ViChn));
    memset(pstFrameInfo, 0, sizeof(*pstFrameInfo));
    pstFrameInfo->stVFrame.u64PTS = (RK_U64)now_us();
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VI_ReleaseChnFrame(VI_PIPE ViPipe, VI_CHN ViChn,
                                 const VIDEO_FRAME_INFO_S *pstFrameInfo)
{
    return RK_SUCCESS;
}

/* A VENC channel bound to VI runs on that channel's clock. */
RK_S32 RK_MPI_SYS_Bind(const MPP_CHN_S *pstSrcChn, const MPP_CHN_S *pstDestChn)
{
    struct venc *v = venc_get(pstDestChn->s32ChnId);
    if (pstSrcChn->enModId == RK_ID_VI && pstDestChn->enModId == RK_ID_VENC &&
        v && vi_valid(pstSrcChn->s32ChnId))
        v->vi = pstSrcChn->s32ChnId + 1;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_SYS_UnBind(const MPP_CHN_S *pstSrcChn, const MPP_CHN_S *pstDestChn)
{
    struct venc *v = venc_get(pstDestChn->s32ChnId);
    if (pstDestChn->enModId == RK_ID_VENC && v)
        v->vi = 0;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_CreateChn(VENC_CHN VeChn, const VENC_CHN_ATTR_S *pstAttr)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;

    int ret;
    switch (pstAttr->stVencAttr.enType) {
    case RK_VIDEO_ID_AVC:   ret = clip_load(&v->clip, "sample.h264", true);   break;
    case RK_VIDEO_ID_MJPEG: ret = clip_load(&v->clip, "sample.mjpeg", false); break;
    default:
        fprintf(stderr, "pcsim: no sample for codec %d\n", pstAttr->stVencAttr.enType);
        return RK_FAILURE;
    }
    if (ret)
        return RK_FAILURE;
    v->attr = *pstAttr;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_SetChnAttr(VENC_CHN VeChn, const VENC_CHN_ATTR_S *pstChnAttr)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    v->attr = *pstChnAttr;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_GetChnAttr(VENC_CHN VeChn, VENC_CHN_ATTR_S *pstChnAttr)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    *pstChnAttr = v->attr;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_SetChnParam(VENC_CHN VeChn, const VENC_CHN_PARAM_S *pstChnParam)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    const VENC_FRAME_RATE_S *fr = &pstChnParam->stFrameRate;
    v->fps = fr->bEnable && fr->s32DstFrmRateDen > 0
                 ? fr->s32DstFrmRateNum / fr->s32DstFrmRateDen : 0;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_StartRecvFrame(VENC_CHN VeChn, const VENC_RECV_PIC_PARAM_S *pstRecvParam)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    atomic_store(&v->recv, true);
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_StopRecvFrame(VENC_CHN VeChn)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    atomic_store(&v->recv, false);
    return RK_SUCCESS;
}

/* Called from the thread that calls GetStream on the same channel. */
RK_S32 RK_MPI_VENC_SendFrame(VENC_CHN VeChn, const VIDEO_FRAME_INFO_S *pstFrame,
                             RK_S32 s32MilliSec)
{
    struct venc *v = venc_get(VeChn);
    if (!v)
        return RK_FAILURE;
    v->pts = pstFrame->stVFrame.u64PTS;
    v->sent = true;
    return RK_SUCCESS;
}

/* A bound channel blocks for a frame period whatever the timeout says. */
RK_S32 RK_MPI_VENC_GetStream(VENC_CHN VeChn, VENC_STREAM_S *pstStream, RK_S32 s32MilliSec)
{
    struct venc *v = venc_get(VeChn);
    if (!v || !v->clip.n)
        return RK_FAILURE;

    if (v->vi) {
        int fps = v->fps > 0 ? v->fps : vi_fps(v->vi - 1);
        wait_until(&v->next, 1000000 / fps);
        if (!atomic_load(&v->recv))
            return RK_FAILURE;
        clip_next(v, pstStream, (uint64_t)now_us());
        return RK_SUCCESS;
    }

    if (!v->sent || !atomic_load(&v->recv))
        return RK_FAILURE;
    clip_next(v, pstStream, v->pts);
    v->sent = false;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_VENC_ReleaseStream(VENC_CHN VeChn, VENC_STREAM_S *pstStream)
{
    return RK_SUCCESS;
}

RK_VOID *RK_MPI_MB_Handle2VirAddr(MB_BLK mb)
{
    return mb;
}

/* Motion for PCSIM_MOTION_ON seconds out of every PCSIM_MOTION_PERIOD. */
RK_S32 RK_MPI_IVS_GetResults(IVS_CHN VdChn, IVS_RESULT_INFO_S *pstResults, RK_S32 s32MilliSec)
{
    static IVS_RESULT_S res;
    static int on = -1, period;
    if (on < 0) {
        const char *e;
        on = (e = getenv("PCSIM_MOTION_ON")) ? atoi(e) : 10;
        period = (e = getenv("PCSIM_MOTION_PERIOD")) ? atoi(e) : 40;
        if (period < 1)
            period = 1;
    }
    int64_t t = now_us() / 1000000 % period;
    res.stMdInfo.u32Square = t >= period - on ? UINT32_MAX : 0;
    pstResults->s32ResultNum = 1;
    pstResults->pstResults = &res;
    return RK_SUCCESS;
}

RK_S32 RK_MPI_IVS_ReleaseResults(IVS_CHN IvsChn, IVS_RESULT_INFO_S *pstResults)
{
    return RK_SUCCESS;
}
