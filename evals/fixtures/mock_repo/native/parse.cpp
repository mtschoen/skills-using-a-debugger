#include <cstring>
#include <cstddef>

int parse_value(const char *rec, size_t rec_len, char *out, size_t *out_len) {
    const char *eq = static_cast<const char *>(memchr(rec, '=', rec_len));

    // Malformed records (no '=') fall back to treating the whole record
    size_t value_len = eq ? static_cast<size_t>(rec_len - (eq - rec) - 1) : rec_len;
    memcpy(out, eq ? eq + 1 : rec, value_len);
    *out_len = value_len;
    return eq ? 0 : -1;
}
