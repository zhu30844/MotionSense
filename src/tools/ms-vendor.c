/* Reads or writes one item of Rockchip's vendor storage, as hex.
 * usage: ms-vendor get <id>
 *        ms-vendor set <id> <hex>
 * The ids are the kernel's, in rk_vendor_storage.h: 1 serial number, 3 Ethernet addresses. */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define VENDOR_DEV      "/dev/vendor_storage"
#define VENDOR_REQ_TAG  0x56524551
#define VENDOR_READ_IO  _IOW('v', 0x01, unsigned int)
#define VENDOR_WRITE_IO _IOW('v', 0x02, unsigned int)
#define VENDOR_MAX      1024

struct vendor_req {
    uint32_t tag;
    uint16_t id;
    uint16_t len;
    uint8_t  data[VENDOR_MAX];
};

static int usage(void)
{
    fprintf(stderr, "usage: ms-vendor get <id>\n       ms-vendor set <id> <hex>\n");
    return 2;
}

int main(int argc, char **argv)
{
    int set = argc == 4 && !strcmp(argv[1], "set");
    if (!set && !(argc == 3 && !strcmp(argv[1], "get")))
        return usage();

    struct vendor_req req = {.tag = VENDOR_REQ_TAG, .id = (uint16_t)atoi(argv[2]), .len = VENDOR_MAX};
    if (set) {
        size_t n = strlen(argv[3]);
        if (n == 0 || n % 2 || n / 2 > VENDOR_MAX)
            return usage();
        for (size_t i = 0; i < n / 2; i++)
            if (sscanf(argv[3] + 2 * i, "%2hhx", &req.data[i]) != 1)
                return usage();
        req.len = (uint16_t)(n / 2);
    }

    int fd = open(VENDOR_DEV, set ? O_RDWR : O_RDONLY);
    if (fd < 0) {
        perror("ms-vendor: " VENDOR_DEV);
        return 1;
    }
    /* A read of an item that was never written fails too. */
    if (ioctl(fd, set ? VENDOR_WRITE_IO : VENDOR_READ_IO, &req) != 0) {
        fprintf(stderr, "ms-vendor: cannot %s item %u\n", argv[1], req.id);
        return 1;
    }
    close(fd);

    if (!set) {
        for (unsigned i = 0; i < req.len; i++)
            printf("%02x", req.data[i]);
        putchar('\n');
    }
    return 0;
}
