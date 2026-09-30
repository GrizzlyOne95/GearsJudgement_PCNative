/* Minimal libmspack system interface used by the standalone LZX decoder. */
#ifndef MSPACK_MINIMAL_H
#define MSPACK_MINIMAL_H 1

#include <stddef.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

struct mspack_file { int dummy; };
struct mspack_system {
  struct mspack_file *(*open)(struct mspack_system *, const char *, int);
  void (*close)(struct mspack_file *);
  int (*read)(struct mspack_file *, void *, int);
  int (*write)(struct mspack_file *, void *, int);
  int (*seek)(struct mspack_file *, off_t, int);
  off_t (*tell)(struct mspack_file *);
  void (*message)(struct mspack_file *, const char *, ...);
  void *(*alloc)(struct mspack_system *, size_t);
  void (*free)(void *);
  void (*copy)(void *, void *, size_t);
  void *null_ptr;
};

#define MSPACK_SYS_SEEK_START (0)
#define MSPACK_SYS_SEEK_CUR   (1)
#define MSPACK_SYS_SEEK_END   (2)

#define MSPACK_ERR_OK          (0)
#define MSPACK_ERR_ARGS        (1)
#define MSPACK_ERR_OPEN        (2)
#define MSPACK_ERR_READ        (3)
#define MSPACK_ERR_WRITE       (4)
#define MSPACK_ERR_SEEK        (5)
#define MSPACK_ERR_NOMEMORY    (6)
#define MSPACK_ERR_SIGNATURE   (7)
#define MSPACK_ERR_DATAFORMAT  (8)
#define MSPACK_ERR_CHECKSUM    (9)
#define MSPACK_ERR_CRUNCH      (10)
#define MSPACK_ERR_DECRUNCH    (11)

#ifdef __cplusplus
}
#endif
#endif
