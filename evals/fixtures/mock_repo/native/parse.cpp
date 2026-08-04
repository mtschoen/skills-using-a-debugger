#include <cstdio>
#include <cstring>

// Parses a "key=value" record. Returns the value pointer, or writes the
// parsed length into *out_len. Crashes on some inputs - reported as a segfault.
const char* parse_value(const char* record, int* out_len) {
    const char* eq = strchr(record, '=');
    const char* value = eq + 1;            // no null check on eq
    *out_len = (int)strlen(value);
    return value;
}

int main(int argc, char** argv) {
    int len = 0;
    for (int i = 1; i < argc; ++i) {
        const char* v = parse_value(argv[i], &len);
        printf("value=%s len=%d\n", v, len);
    }
    return 0;
}
