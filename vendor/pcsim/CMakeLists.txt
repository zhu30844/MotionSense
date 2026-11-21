# Rockchip's media API over sample files, to run the daemon on a PC.
add_library(pcsim STATIC
    src/stream.c
    src/stubs.c
)

# Compiled against the real headers.
foreach(_rk rk::rockit rk::rkaiq rk::mpp)
    get_target_property(_inc ${_rk} INTERFACE_INCLUDE_DIRECTORIES)
    target_include_directories(pcsim PUBLIC ${_inc})
endforeach()

target_compile_definitions(pcsim PRIVATE
    PCSIM_SAMPLE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/sample")
