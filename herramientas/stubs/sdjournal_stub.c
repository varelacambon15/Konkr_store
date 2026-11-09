/* Sustituto mínimo para Box64: WebKit (libjavascriptcoregtk) importa sd_journal_send_with_location de libsystemd,
 * y Box64 no la envuelve en SteamOS ARM. Solo escribe en el diario del sistema: aquí no hace nada y devuelve 0 (éxito).
 * Se carga con BOX64_LD_PRELOAD (lanzar_recomp.sh). Compilar: gcc -shared -fPIC -O2 -o sdjournal_stub_x86_64.so sdjournal_stub.c */
int sd_journal_send_with_location(const char *file, const char *line, const char *func, const char *format, ...) {
    (void)file; (void)line; (void)func; (void)format;
    return 0;
}
