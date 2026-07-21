import sys
import math
import random
import numpy as np
import pygame

WIDTH, HEIGHT = 500, 800
FPS = 60

CIRCLE_MARGIN = 40
CIRCLE_RADIUS = WIDTH // 2 - CIRCLE_MARGIN
CIRCLE_CENTER = (WIDTH // 2, HEIGHT // 2)
CIRCLE_THICKNESS = 4

# ---------- ball ----------
BALL_RADIUS = 14
GRAVITY = 0.35                     # gently curves the path, doesn't change speed
BASE_SPEED = 5.0                   # pixels/frame at the start
SPEED_INCREASE_PER_BOUNCE = 0.6    # permanent speed gain, every single touch
MAX_SPEED = 450.0                   # cap so it stays visually readable
RANDOM_ANGLE_SPREAD = 0.9          # radians of random "wobble" added on bounce (~51 deg)

BG_COLOR = (15, 15, 25)
CIRCLE_COLOR = (90, 200, 255)
BALL_COLOR_CALM = (80, 220, 120)
BALL_COLOR_CRAZY = (255, 60, 60)

# ---------- audio ----------
SAMPLE_RATE = 44100
NUM_BOUNCE_SOUNDS = 16      # pitch buckets, quantized by "craziness"
BOUNCE_FREQ_LOW = 260.0     # Hz, calm bounce
BOUNCE_FREQ_HIGH = 1100.0   # Hz, berserk bounce
WARNING_THRESHOLD = 0.9     # fraction of MAX_SPEED that triggers the one-time alarm


def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def normalize(vx, vy):
    length = math.hypot(vx, vy)
    if length == 0:
        return 0.0, 1.0
    return vx / length, vy / length


def rotate(vx, vy, angle):
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return vx * cos_a - vy * sin_a, vx * sin_a + vy * cos_a


def make_tone(freq, duration=0.14, volume=0.5, decay=7.0, harmonic=0.3):
    """A short, bell-like decaying tone -- used for bounces/chimes."""
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, False)
    wave = np.sin(2 * np.pi * freq * t)
    wave += harmonic * np.sin(2 * np.pi * freq * 2 * t)
    envelope = np.exp(-decay * t)
    wave *= envelope
    peak = np.max(np.abs(wave))
    if peak > 0:
        wave /= peak
    samples = (wave * volume * 32767).astype(np.int16)
    stereo = np.column_stack([samples, samples])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def make_alarm():
    """A short two-tone 'warning' blip."""
    n = int(SAMPLE_RATE * 0.35)
    t = np.linspace(0, 0.35, n, False)
    freq_sweep = 700 + 500 * np.sign(np.sin(2 * np.pi * 6 * t))
    phase = 2 * np.pi * np.cumsum(freq_sweep) / SAMPLE_RATE
    wave = np.sin(phase)
    envelope = np.clip(1.2 - t, 0, 1)
    wave *= envelope
    peak = np.max(np.abs(wave))
    if peak > 0:
        wave /= peak
    samples = (wave * 0.5 * 32767).astype(np.int16)
    stereo = np.column_stack([samples, samples])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def make_whoosh(duration=2.0):
    n = int(SAMPLE_RATE * duration)
    noise = np.random.uniform(-1, 1, n)
    kernel_size = 250
    kernel = np.ones(kernel_size) / kernel_size
    filtered = np.convolve(noise, kernel, mode="same")
    peak = np.max(np.abs(filtered))
    if peak > 0:
        filtered /= peak
    samples = (filtered * 0.35 * 32767).astype(np.int16)
    stereo = np.column_stack([samples, samples])
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def main():
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 256)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Last BrainCell")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)

    bounce_sounds = []
    for i in range(NUM_BOUNCE_SOUNDS):
        frac = i / (NUM_BOUNCE_SOUNDS - 1)
        freq = BOUNCE_FREQ_LOW + (BOUNCE_FREQ_HIGH - BOUNCE_FREQ_LOW) * frac
        vol = 0.35 + 0.45 * frac
        bounce_sounds.append(make_tone(freq, duration=0.13, volume=vol, decay=8.0))

    milestone_sound = make_tone(1500, duration=0.35, volume=0.55, decay=3.0, harmonic=0.6)
    alarm_sound = make_alarm()
    whoosh_sound = make_whoosh()

    whoosh_channel = pygame.mixer.Channel(0)
    whoosh_channel.play(whoosh_sound, loops=-1)
    whoosh_channel.set_volume(0.0)

    ball_pos = [float(CIRCLE_CENTER[0]), float(CIRCLE_CENTER[1])]
    direction = [0.0, 1.0]
    speed = BASE_SPEED

    bounce_count = 0
    warning_played = False
    max_dist = CIRCLE_RADIUS - BALL_RADIUS

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        nudged = (direction[0] * speed, direction[1] * speed + GRAVITY)
        direction[0], direction[1] = normalize(*nudged)

        ball_pos[0] += direction[0] * speed
        ball_pos[1] += direction[1] * speed

        dx = ball_pos[0] - CIRCLE_CENTER[0]
        dy = ball_pos[1] - CIRCLE_CENTER[1]
        dist_from_center = math.hypot(dx, dy)

        craziness = (speed - BASE_SPEED) / (MAX_SPEED - BASE_SPEED)
        craziness = max(0.0, min(1.0, craziness))

        if dist_from_center > max_dist:
            nx, ny = dx / dist_from_center, dy / dist_from_center

            ball_pos[0] = CIRCLE_CENTER[0] + nx * max_dist
            ball_pos[1] = CIRCLE_CENTER[1] + ny * max_dist

            dot = direction[0] * nx + direction[1] * ny
            rx = direction[0] - 2 * dot * nx
            ry = direction[1] - 2 * dot * ny

            wobble = random.uniform(-RANDOM_ANGLE_SPREAD, RANDOM_ANGLE_SPREAD)
            rx, ry = rotate(rx, ry, wobble)
            direction[0], direction[1] = normalize(rx, ry)

            speed = min(MAX_SPEED, speed + SPEED_INCREASE_PER_BOUNCE)
            bounce_count += 1

            bucket = int(craziness * (NUM_BOUNCE_SOUNDS - 1))
            bounce_sounds[bucket].play()

            # --- milestone chime every 10 bounces ---
            # if bounce_count % 10 == 0:
            #     milestone_sound.play()

            if not warning_played and speed >= WARNING_THRESHOLD * MAX_SPEED:
                alarm_sound.play()
                warning_played = True

        whoosh_channel.set_volume(0.05 + 0.35 * craziness)

        screen.fill(BG_COLOR)
        pygame.draw.circle(screen, CIRCLE_COLOR, CIRCLE_CENTER, CIRCLE_RADIUS, CIRCLE_THICKNESS)

        ball_color = lerp_color(BALL_COLOR_CALM, BALL_COLOR_CRAZY, craziness)
        pygame.draw.circle(screen, ball_color, (int(ball_pos[0]), int(ball_pos[1])), BALL_RADIUS)

        # hud = font.render(
        #     f"Bounces: {bounce_count}   Speed: {speed:.1f} px/frame", True, (220, 220, 220)
        # )
        # screen.blit(hud, (16, 16))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()