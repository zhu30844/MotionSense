/* Calls media.c makes that need no behaviour here. */
#include <stdbool.h>
#include <string.h>

#include "rk_aiq_user_api2_sysctl.h"
#include "rk_mpi_ivs.h"
#include "rk_mpi_rgn.h"
#include "rk_mpi_sys.h"
#include "rk_mpi_venc.h"
#include "rk_mpi_vi.h"

#define OK(proto)      proto { return RK_SUCCESS; }
#define ZERO(proto, p) proto { memset(p, 0, sizeof(*p)); return RK_SUCCESS; }

OK(RK_S32 RK_MPI_SYS_Init(RK_VOID))
OK(RK_S32 RK_MPI_SYS_Exit(RK_VOID))

ZERO(RK_S32 RK_MPI_VI_GetDevAttr(VI_DEV ViDev, VI_DEV_ATTR_S *pstDevAttr), pstDevAttr)
OK(RK_S32 RK_MPI_VI_SetDevAttr(VI_DEV ViDev, const VI_DEV_ATTR_S *pstDevAttr))
OK(RK_S32 RK_MPI_VI_GetDevIsEnable(VI_DEV ViDev))
OK(RK_S32 RK_MPI_VI_EnableDev(VI_DEV ViDev))
OK(RK_S32 RK_MPI_VI_DisableDev(VI_DEV ViDev))
OK(RK_S32 RK_MPI_VI_SetDevBindPipe(VI_DEV ViDev, const VI_DEV_BIND_PIPE_S *pstDevBindPipe))
OK(RK_S32 RK_MPI_VI_EnableChn(VI_PIPE ViPipe, VI_CHN ViChn))
OK(RK_S32 RK_MPI_VI_DisableChn(VI_PIPE ViPipe, VI_CHN ViChn))

OK(RK_S32 RK_MPI_VENC_DestroyChn(VENC_CHN VeChn))
ZERO(RK_S32 RK_MPI_VENC_GetRcParam(VENC_CHN VeChn, VENC_RC_PARAM_S *pstRcParam), pstRcParam)
OK(RK_S32 RK_MPI_VENC_SetRcParam(VENC_CHN VeChn, const VENC_RC_PARAM_S *pstRcParam))
ZERO(RK_S32 RK_MPI_VENC_GetAntiLine(VENC_CHN VeChn, VENC_ANTI_LINE_S *pstAntiLine), pstAntiLine)
OK(RK_S32 RK_MPI_VENC_SetAntiLine(VENC_CHN VeChn, const VENC_ANTI_LINE_S *pstAntiLine))
ZERO(RK_S32 RK_MPI_VENC_GetAntiRing(VENC_CHN VeChn, VENC_ANTI_RING_S *pstAntiRing), pstAntiRing)
OK(RK_S32 RK_MPI_VENC_SetAntiRing(VENC_CHN VeChn, const VENC_ANTI_RING_S *pstAntiRing))
ZERO(RK_S32 RK_MPI_VENC_GetFilter(VENC_CHN VeChn, VENC_FILTER_S *pstFilter), pstFilter)
OK(RK_S32 RK_MPI_VENC_SetFilter(VENC_CHN VeChn, const VENC_FILTER_S *pstFilter))
ZERO(RK_S32 RK_MPI_VENC_GetLambda(VENC_CHN VeChn, VENC_LAMBDA_S *pstLambda), pstLambda)
OK(RK_S32 RK_MPI_VENC_SetLambda(VENC_CHN VeChn, const VENC_LAMBDA_S *pstLambda))
OK(RK_S32 RK_MPI_VENC_SetDeBreathEffect(VENC_CHN VeChn, const VENC_DEBREATHEFFECT_S *pstDeBreathEffect))
OK(RK_S32 RK_MPI_VENC_EnableMotionDeblur(VENC_CHN VeChn, RK_BOOL bEnable))
OK(RK_S32 RK_MPI_VENC_SetMotionDeblurStrength(VENC_CHN VeChn, const RK_U32 u32Strength))

OK(RK_S32 RK_MPI_IVS_CreateChn(IVS_CHN IvsChn, IVS_CHN_ATTR_S *pstAttr))
OK(RK_S32 RK_MPI_IVS_DestroyChn(IVS_CHN IvsChn))
ZERO(RK_S32 RK_MPI_IVS_GetMdAttr(IVS_CHN IvsChn, IVS_MD_ATTR_S *pstMdAttr), pstMdAttr)
OK(RK_S32 RK_MPI_IVS_SetMdAttr(IVS_CHN IvsChn, IVS_MD_ATTR_S *pstMdAttr))

OK(RK_S32 RK_MPI_RGN_Create(RGN_HANDLE Handle, const RGN_ATTR_S *pstRegion))
OK(RK_S32 RK_MPI_RGN_Destroy(RGN_HANDLE Handle))
OK(RK_S32 RK_MPI_RGN_AttachToChn(RGN_HANDLE Handle, const MPP_CHN_S *pstChn, const RGN_CHN_ATTR_S *pstChnAttr))
OK(RK_S32 RK_MPI_RGN_DetachFromChn(RGN_HANDLE Handle, const MPP_CHN_S *pstChn))
OK(RK_S32 RK_MPI_RGN_SetBitMap(RGN_HANDLE Handle, const BITMAP_S *pstBitmap))

static int s_aiq;

XCamReturn rk_aiq_uapi2_sysctl_enumStaticMetasByPhyId(int index, rk_aiq_static_info_t *static_info)
{
    memset(static_info, 0, sizeof(*static_info));
    strcpy(static_info->sensor_info.sensor_name, "pcsim");
    return XCAM_RETURN_NO_ERROR;
}

XCamReturn rk_aiq_uapi2_sysctl_preInit_devBufCnt(const char *sns_ent_name, const char *dev_ent, int buf_cnt)
{
    return XCAM_RETURN_NO_ERROR;
}

rk_aiq_sys_ctx_t *rk_aiq_uapi2_sysctl_init(const char *sns_ent_name, const char *iq_file_dir,
                                           rk_aiq_error_cb err_cb, rk_aiq_metas_cb metas_cb)
{
    return (rk_aiq_sys_ctx_t *)&s_aiq;
}

XCamReturn rk_aiq_uapi2_sysctl_prepare(const rk_aiq_sys_ctx_t *ctx, uint32_t width, uint32_t height,
                                       rk_aiq_working_mode_t mode)
{
    return XCAM_RETURN_NO_ERROR;
}

XCamReturn rk_aiq_uapi2_sysctl_start(const rk_aiq_sys_ctx_t *ctx)
{
    return XCAM_RETURN_NO_ERROR;
}

XCamReturn rk_aiq_uapi2_sysctl_stop(const rk_aiq_sys_ctx_t *ctx, bool keep_ext_hw_st)
{
    return XCAM_RETURN_NO_ERROR;
}

void rk_aiq_uapi2_sysctl_deinit(rk_aiq_sys_ctx_t *ctx)
{
}
