// MMUKO freestanding QEMU kernel.
// This file has no libc dependency: no printf, malloc, calloc, or file I/O.

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define MMUKO_VERSION "0.1-qemu"
#define MMUKO_MEMORY_SIZE 16

#define VGA_WIDTH 80
#define VGA_HEIGHT 25
#define VGA_MEMORY ((volatile uint16_t *)0xB8000)
#define COM1 0x3F8

typedef enum {
    N,
    NE,
    E,
    SE,
    S,
    SW,
    W,
    NW,
    UNDEFINED_DIR
} Direction;

typedef enum {
    UP,
    DOWN,
    CHARM,
    STRANGE,
    LEFT,
    RIGHT
} State;

typedef enum {
    BOOT_OK,
    BOOT_LOCK_DETECTED,
    BOOT_ROTATION_LOCK,
    BOOT_FAILED
} BootStatus;

typedef struct {
    int index;
    uint8_t value;
    uint16_t spin_mrad;
    Direction direction;
    State state;
    bool superposed;
    int entangled_with;
} Cubit;

typedef struct {
    uint8_t raw_value;
    Cubit cubit_ring[8];
    int base_index;
    Direction primary_superposition;
    Direction secondary_superposition;
} MMUKO_Byte;

typedef struct {
    uint16_t gravity_milli;
    uint16_t air_milli;
    uint16_t water_milli;
} VacuumMedium;

typedef struct {
    MMUKO_Byte *memory_map;
    size_t memory_size;
    VacuumMedium medium;
    Direction frame_of_reference;
    bool boot_complete;
} MMUKO_System;

typedef struct {
    int base;
    Direction primary;
    Direction secondary;
} SuperpositionEntry;

static MMUKO_System g_system;
static MMUKO_Byte g_memory[MMUKO_MEMORY_SIZE];
static size_t g_vga_row;
static size_t g_vga_col;
static uint8_t g_vga_color = 0x0F;

static const char *const direction_names[] = {
    "NORTH", "NORTHEAST", "EAST", "SOUTHEAST",
    "SOUTH", "SOUTHWEST", "WEST", "NORTHWEST", "UNDEFINED"
};

static const char *const state_names[] = {
    "UP", "DOWN", "CHARM", "STRANGE", "LEFT", "RIGHT"
};

static const uint16_t spin_mrad_values[] = {
    785, 1047, 1571, 3142, 6283, 1571, 1047, 785
};

static const Direction direction_values[] = {
    N, NE, E, SE, S, SW, W, NW
};

static const int entangled_pairs[] = {
    7, 6, 5, -1, -1, 2, 1, 0
};

static const SuperpositionEntry superposition_table[] = {
    {12, S, N},
    {10, SE, N},
    {8, E, W},
    {6, SW, E},
    {4, W, E},
    {2, NE, W},
    {1, N, S}
};

static inline void outb(uint16_t port, uint8_t value)
{
    __asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}

static inline uint8_t inb(uint16_t port)
{
    uint8_t value;
    __asm__ volatile("inb %1, %0" : "=a"(value) : "Nd"(port));
    return value;
}

static void serial_init(void)
{
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x80);
    outb(COM1 + 0, 0x03);
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x03);
    outb(COM1 + 2, 0xC7);
    outb(COM1 + 4, 0x0B);
}

static bool serial_ready(void)
{
    return (inb(COM1 + 5) & 0x20) != 0;
}

static void serial_write_char(char c)
{
    while (!serial_ready()) {
    }
    outb(COM1, (uint8_t)c);
}

static void vga_clear(void)
{
    uint16_t blank = ((uint16_t)g_vga_color << 8) | ' ';
    for (size_t y = 0; y < VGA_HEIGHT; y++) {
        for (size_t x = 0; x < VGA_WIDTH; x++) {
            VGA_MEMORY[y * VGA_WIDTH + x] = blank;
        }
    }
    g_vga_row = 0;
    g_vga_col = 0;
}

static void put_char(char c)
{
    if (c == '\n') {
        serial_write_char('\r');
        serial_write_char('\n');
        g_vga_col = 0;
        if (++g_vga_row == VGA_HEIGHT) {
            g_vga_row = 0;
        }
        return;
    }

    serial_write_char(c);
    VGA_MEMORY[g_vga_row * VGA_WIDTH + g_vga_col] =
        ((uint16_t)g_vga_color << 8) | (uint8_t)c;

    if (++g_vga_col == VGA_WIDTH) {
        g_vga_col = 0;
        if (++g_vga_row == VGA_HEIGHT) {
            g_vga_row = 0;
        }
    }
}

static void puts_kernel(const char *text)
{
    while (*text != '\0') {
        put_char(*text++);
    }
}

static void put_dec_u32(uint32_t value)
{
    char buffer[11];
    size_t used = 0;

    if (value == 0) {
        put_char('0');
        return;
    }

    while (value > 0 && used < sizeof(buffer)) {
        buffer[used++] = (char)('0' + (value % 10));
        value /= 10;
    }

    while (used > 0) {
        put_char(buffer[--used]);
    }
}

static void put_hex_u32(uint32_t value)
{
    static const char hex[] = "0123456789ABCDEF";
    puts_kernel("0x");
    for (int shift = 28; shift >= 0; shift -= 4) {
        put_char(hex[(value >> shift) & 0xF]);
    }
}

static int iabs(int value)
{
    return value < 0 ? -value : value;
}

static const char *direction_to_string(Direction dir)
{
    if (dir >= N && dir <= UNDEFINED_DIR) {
        return direction_names[dir];
    }
    return "INVALID";
}

static const char *state_to_string(State state)
{
    if (state >= UP && state <= RIGHT) {
        return state_names[state];
    }
    return "INVALID";
}

static VacuumMedium init_vacuum_medium(void)
{
    VacuumMedium medium = {
        .gravity_milli = 9800,
        .air_milli = 0,
        .water_milli = 0,
    };

    puts_kernel("[PHASE 0] Vacuum medium initialized: G=");
    put_dec_u32(medium.gravity_milli);
    puts_kernel(" milli-g\n");
    return medium;
}

static State resolve_state(int index, uint8_t byte_value)
{
    uint8_t bit = (byte_value >> index) & 1;
    uint8_t neighbor = (byte_value >> ((index + 1) & 7)) & 1;

    if (bit == 1 && neighbor == 1) {
        return UP;
    }
    if (bit == 1 && neighbor == 0) {
        return CHARM;
    }
    if (bit == 0 && neighbor == 1) {
        return STRANGE;
    }
    return DOWN;
}

static void init_cubit_ring(MMUKO_Byte *byte)
{
    for (int i = 0; i < 8; i++) {
        Cubit *c = &byte->cubit_ring[i];
        c->index = i;
        c->value = (byte->raw_value >> i) & 1;
        c->spin_mrad = spin_mrad_values[i];
        c->direction = direction_values[i];
        c->state = resolve_state(i, byte->raw_value);
        c->entangled_with = entangled_pairs[i];
        c->superposed = c->entangled_with != -1;
    }
}

static int round_to_known_base(int base)
{
    static const int valid_bases[] = {12, 10, 8, 6, 4, 2, 1};
    int nearest = valid_bases[0];
    int min_diff = iabs(base - valid_bases[0]);

    for (size_t i = 1; i < sizeof(valid_bases) / sizeof(valid_bases[0]); i++) {
        int diff = iabs(base - valid_bases[i]);
        if (diff < min_diff) {
            min_diff = diff;
            nearest = valid_bases[i];
        }
    }

    return nearest;
}

static void lookup_superposition(int base, Direction *primary, Direction *secondary)
{
    size_t table_size = sizeof(superposition_table) / sizeof(superposition_table[0]);

    for (size_t i = 0; i < table_size; i++) {
        if (superposition_table[i].base == base) {
            *primary = superposition_table[i].primary;
            *secondary = superposition_table[i].secondary;
            return;
        }
    }

    int nearest = round_to_known_base(base);
    for (size_t i = 0; i < table_size; i++) {
        if (superposition_table[i].base == nearest) {
            *primary = superposition_table[i].primary;
            *secondary = superposition_table[i].secondary;
            return;
        }
    }

    *primary = N;
    *secondary = S;
}

static uint8_t rotate_bits(uint8_t value, unsigned int n)
{
    n &= 7;
    if (n == 0) {
        return value;
    }
    return (uint8_t)(((value >> n) | (value << (8 - n))) & 0xFF);
}

static Direction resolve_direction_from_neighbors(MMUKO_Byte *byte, int cubit_index)
{
    int direction_count[8] = {0};
    int max_count = 0;
    Direction max_direction = N;

    for (int offset = -1; offset <= 1; offset++) {
        if (offset == 0) {
            continue;
        }

        int neighbor_index = (cubit_index + offset + 8) & 7;
        Direction neighbor_direction = byte->cubit_ring[neighbor_index].direction;

        if (neighbor_direction != UNDEFINED_DIR) {
            direction_count[neighbor_direction]++;
            if (direction_count[neighbor_direction] > max_count) {
                max_count = direction_count[neighbor_direction];
                max_direction = neighbor_direction;
            }
        }
    }

    return max_count == 0 ? N : max_direction;
}

static State flip_state(State state)
{
    switch (state) {
        case UP:
            return DOWN;
        case DOWN:
            return UP;
        case CHARM:
            return STRANGE;
        case STRANGE:
            return CHARM;
        case LEFT:
            return RIGHT;
        case RIGHT:
            return LEFT;
        default:
            return state;
    }
}

static Cubit *get_cubit_from_byte(MMUKO_Byte *byte, int index)
{
    if (index >= 0 && index < 8) {
        return &byte->cubit_ring[index];
    }
    return NULL;
}

static BootStatus phase1_cubit_init(MMUKO_System *sys)
{
    puts_kernel("[PHASE 1] Initializing cubit rings...\n");

    for (size_t i = 0; i < sys->memory_size; i++) {
        uint8_t value = sys->memory_map[i].raw_value;
        sys->memory_map[i].base_index = (value % 12) + 1;

        init_cubit_ring(&sys->memory_map[i]);
        lookup_superposition(sys->memory_map[i].base_index,
                             &sys->memory_map[i].primary_superposition,
                             &sys->memory_map[i].secondary_superposition);
    }

    puts_kernel("[PHASE 1] Initialized ");
    put_dec_u32((uint32_t)sys->memory_size);
    puts_kernel(" cubit rings\n");
    return BOOT_OK;
}

static BootStatus phase2_compass_alignment(MMUKO_System *sys)
{
    puts_kernel("[PHASE 2] Compass alignment...\n");

    for (size_t b = 0; b < sys->memory_size; b++) {
        MMUKO_Byte *byte = &sys->memory_map[b];
        for (int i = 0; i < 8; i++) {
            Cubit *c = &byte->cubit_ring[i];
            if (c->direction == UNDEFINED_DIR) {
                c->direction = resolve_direction_from_neighbors(byte, i);
                if (c->direction == UNDEFINED_DIR) {
                    puts_kernel("[ERROR] Boot lock detected\n");
                    return BOOT_LOCK_DETECTED;
                }
            }
        }
    }

    puts_kernel("[PHASE 2] All cubits aligned to compass directions\n");
    return BOOT_OK;
}

static BootStatus phase3_superposition_entanglement(MMUKO_System *sys)
{
    puts_kernel("[PHASE 3] Entangling superposition pairs...\n");

    for (size_t b = 0; b < sys->memory_size; b++) {
        MMUKO_Byte *byte = &sys->memory_map[b];
        for (int i = 0; i < 8; i++) {
            Cubit *c = &byte->cubit_ring[i];
            if (c->superposed && c->entangled_with != -1) {
                Cubit *partner = get_cubit_from_byte(byte, c->entangled_with);
                if (partner != NULL && c->state == partner->state) {
                    partner->state = flip_state(partner->state);
                }
            }
        }
    }

    puts_kernel("[PHASE 3] Superposition entanglement complete\n");
    return BOOT_OK;
}

static BootStatus phase4_frame_centering(MMUKO_System *sys)
{
    Direction primary;
    Direction secondary;

    puts_kernel("[PHASE 4] Frame of reference centering...\n");
    lookup_superposition(6, &primary, &secondary);
    sys->frame_of_reference = primary;

    for (size_t i = 0; i < sys->memory_size; i++) {
        sys->memory_map[i].primary_superposition = primary;
        sys->memory_map[i].secondary_superposition = secondary;
    }

    puts_kernel("[PHASE 4] Frame set to ");
    puts_kernel(direction_to_string(primary));
    puts_kernel("/");
    puts_kernel(direction_to_string(secondary));
    puts_kernel("\n");
    return BOOT_OK;
}

static void resolve_base_state(MMUKO_System *sys, int base)
{
    Direction primary;
    Direction secondary;
    lookup_superposition(base, &primary, &secondary);

    for (size_t i = 0; i < sys->memory_size; i++) {
        if (sys->memory_map[i].base_index == base) {
            sys->memory_map[i].primary_superposition = primary;
            sys->memory_map[i].secondary_superposition = secondary;
        }
    }
}

static BootStatus phase5_nonlinear_resolution(MMUKO_System *sys)
{
    static const int boot_order[] = {12, 6, 8, 4, 10, 2, 1};

    puts_kernel("[PHASE 5] Nonlinear index resolution...\n");
    for (size_t i = 0; i < sizeof(boot_order) / sizeof(boot_order[0]); i++) {
        Direction primary;
        Direction secondary;
        int base = boot_order[i];

        resolve_base_state(sys, base);
        lookup_superposition(base, &primary, &secondary);

        puts_kernel("[PHASE 5] Base ");
        put_dec_u32((uint32_t)base);
        puts_kernel(" -> ");
        puts_kernel(direction_to_string(primary));
        puts_kernel("/");
        puts_kernel(direction_to_string(secondary));
        puts_kernel("\n");
    }

    return BOOT_OK;
}

static BootStatus phase6_rotation_verification(MMUKO_System *sys)
{
    puts_kernel("[PHASE 6] Rotation freedom check...\n");

    for (size_t b = 0; b < sys->memory_size; b++) {
        MMUKO_Byte *byte = &sys->memory_map[b];
        for (int i = 0; i < 8; i++) {
            uint8_t original = byte->cubit_ring[i].value;
            uint8_t test_value = rotate_bits(original, 4);
            test_value = rotate_bits(test_value, 4);

            if (test_value != original) {
                puts_kernel("[ERROR] Rotation lock detected\n");
                return BOOT_ROTATION_LOCK;
            }
        }
    }

    puts_kernel("[PHASE 6] All cubits rotate freely\n");
    return BOOT_OK;
}

static void mmuko_system_init(MMUKO_System *sys, MMUKO_Byte *memory, size_t memory_size)
{
    sys->memory_map = memory;
    sys->memory_size = memory_size;
    sys->frame_of_reference = N;
    sys->boot_complete = false;

    for (size_t i = 0; i < memory_size; i++) {
        memory[i].raw_value = (uint8_t)(i * 17 + 42);
    }
}

static BootStatus mmuko_boot(MMUKO_System *sys)
{
    BootStatus status;

    puts_kernel("\n=== MMUKO BOOT SEQUENCE v" MMUKO_VERSION " ===\n\n");

    sys->medium = init_vacuum_medium();

    status = phase1_cubit_init(sys);
    if (status != BOOT_OK) {
        return status;
    }

    status = phase2_compass_alignment(sys);
    if (status != BOOT_OK) {
        return status;
    }

    status = phase3_superposition_entanglement(sys);
    if (status != BOOT_OK) {
        return status;
    }

    status = phase4_frame_centering(sys);
    if (status != BOOT_OK) {
        return status;
    }

    status = phase5_nonlinear_resolution(sys);
    if (status != BOOT_OK) {
        return status;
    }

    status = phase6_rotation_verification(sys);
    if (status != BOOT_OK) {
        return status;
    }

    puts_kernel("\n[PHASE 7] MMUKO BOOT COMPLETE\n");
    sys->boot_complete = true;
    return BOOT_OK;
}

static void mmuko_print_cubit_state(MMUKO_System *sys, size_t byte_index, int cubit_index)
{
    if (byte_index >= sys->memory_size || cubit_index < 0 || cubit_index >= 8) {
        return;
    }

    Cubit *c = &sys->memory_map[byte_index].cubit_ring[cubit_index];
    puts_kernel("Byte[");
    put_dec_u32((uint32_t)byte_index);
    puts_kernel("].Cubit[");
    put_dec_u32((uint32_t)cubit_index);
    puts_kernel("]: val=");
    put_dec_u32(c->value);
    puts_kernel(", dir=");
    puts_kernel(direction_to_string(c->direction));
    puts_kernel(", state=");
    puts_kernel(state_to_string(c->state));
    puts_kernel(", spin_mrad=");
    put_dec_u32(c->spin_mrad);
    puts_kernel("\n");
}

static uint32_t mmuko_memory_checksum(const MMUKO_System *sys)
{
    uint32_t checksum = 0x4D4D554B;

    for (size_t i = 0; i < sys->memory_size; i++) {
        checksum ^= sys->memory_map[i].raw_value;
        checksum = (checksum << 5) | (checksum >> 27);
        checksum += (uint32_t)sys->memory_map[i].base_index;
    }

    return checksum;
}

static void mmuko_program_main(MMUKO_System *sys)
{
    puts_kernel("\n=== MMUKO PROGRAM START ===\n");
    puts_kernel("[PROGRAM] Hello from a program launched by mmuko_boot.\n");

    uint8_t before = sys->memory_map[0].raw_value;
    sys->memory_map[0].raw_value = rotate_bits(before, 1);
    init_cubit_ring(&sys->memory_map[0]);

    puts_kernel("[PROGRAM] Rotated byte 0: ");
    put_hex_u32(before);
    puts_kernel(" -> ");
    put_hex_u32(sys->memory_map[0].raw_value);
    puts_kernel("\n");

    puts_kernel("[PROGRAM] Memory checksum: ");
    put_hex_u32(mmuko_memory_checksum(sys));
    puts_kernel("\n");

    mmuko_print_cubit_state(sys, 0, 0);
    mmuko_print_cubit_state(sys, 0, 2);
    puts_kernel("=== MMUKO PROGRAM END ===\n");
}

void kernel_main(uint32_t multiboot_magic, uint32_t multiboot_info)
{
    (void)multiboot_magic;
    (void)multiboot_info;

    serial_init();
    vga_clear();

    puts_kernel("MMUKO OS Boot Loader\n");
    puts_kernel("OBINexus R&D\n");

    mmuko_system_init(&g_system, g_memory, MMUKO_MEMORY_SIZE);
    BootStatus status = mmuko_boot(&g_system);

    if (status == BOOT_OK) {
        puts_kernel("\n=== SYSTEM READY ===\n");
        puts_kernel("Frame of reference: ");
        puts_kernel(direction_to_string(g_system.frame_of_reference));
        puts_kernel("\n");
        mmuko_program_main(&g_system);
    } else {
        puts_kernel("\n=== BOOT FAILED ===\nStatus code: ");
        put_dec_u32((uint32_t)status);
        puts_kernel("\n");
    }

    for (;;) {
        __asm__ volatile("hlt");
    }
}
