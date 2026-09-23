// rust_core/src/probe/mod.rs
// High-performance visual analytics for dev_probe
// Moved from Python for 10-50x speedup on frame analysis

use image::{DynamicImage, GenericImageView};
use ndarray::{Array2, Array3};
use num_complex::Complex;
use rustfft::{FftPlanner, Length};

/// Configuration for visual analysis thresholds
/// These can be overridden by Lua config at runtime
#[derive(Debug, Clone)]
pub struct ProbeConfig {
    pub blank_frame_stddev_threshold: f32,
    pub visual_hash_bits: usize,
    pub hamming_threshold: u32,
    pub motion_detection_threshold: f32,
    pub brightness_anomaly_threshold: f32,
    pub entity_tracking_max_distance: f32,
    pub ssim_threshold: f32,
}

impl Default for ProbeConfig {
    fn default() -> Self {
        Self {
            blank_frame_stddev_threshold: 2.0,
            visual_hash_bits: 16,
            hamming_threshold: 8,
            motion_detection_threshold: 5.0,
            brightness_anomaly_threshold: 30.0,
            entity_tracking_max_distance: 150.0,
            ssim_threshold: 0.95,
        }
    }
}

/// Perceptual hash result (256-bit as u64 array for efficiency)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PerceptualHash {
    pub bits: [u64; 4], // 256 bits total
}

impl PerceptualHash {
    pub fn hamming_distance(&self, other: &Self) -> u32 {
        let mut distance = 0u32;
        for i in 0..4 {
            distance += (self.bits[i] ^ other.bits[i]).count_ones();
        }
        distance
    }

    pub fn is_similar(&self, other: &Self, threshold: u32) -> bool {
        self.hamming_distance(other) <= threshold
    }
}

/// Brightness statistics for a frame
#[derive(Debug, Clone)]
pub struct BrightnessStats {
    pub mean: f32,
    pub stddev: f32,
    pub min: u8,
    pub max: u8,
}

/// Motion statistics from optical flow
#[derive(Debug, Clone)]
pub struct MotionStats {
    pub mean_magnitude: f32,
    pub max_magnitude: f32,
    pub std_magnitude: f32,
    pub high_motion_pixels: usize,
    pub motion_ratio: f32,
}

/// Structural Similarity Index result
#[derive(Debug, Clone)]
pub struct SSIMResult {
    pub score: f32,
    pub mean_score: f32,
}

/// Entity position tracking data
#[derive(Debug, Clone)]
pub struct EntityTrack {
    pub entity_id: String,
    pub screen_x: f32,
    pub screen_y: f32,
    pub frame_index: usize,
}

/// Visual analysis results for a single frame
#[derive(Debug, Clone)]
pub struct FrameAnalysis {
    pub perceptual_hash: Option<PerceptualHash>,
    pub brightness: Option<BrightnessStats>,
    pub motion: Option<MotionStats>,
    pub is_blank: bool,
    pub edge_density: f32,
    pub complexity_score: f32,
}

/// Compute perceptual hash using DCT (Discrete Cosine Transform)
/// Much faster than Python+Pillow implementation
pub fn compute_perceptual_hash(
    image: &DynamicImage,
    config: &ProbeConfig,
) -> Option<PerceptualHash> {
    let size = config.visual_hash_bits;
    
    // Convert to grayscale and resize
    let gray = image.to_luma8();
    let resized = image::imageops::resize(
        &gray,
        size as u32,
        size as u32,
        image::imageops::FilterType::Lanczos3,
    );

    // Extract pixel values as f64 for FFT
    let mut pixels: Vec<f64> = Vec::with_capacity(size * size);
    for pixel in resized.pixels() {
        pixels.push(pixel[2] as f64); // Luma channel
    }

    // Compute 2D DCT using FFT (row-column method)
    let dct_result = compute_2d_dct(&pixels, size);

    // Take low-frequency components (excluding DC)
    let mut hash_bits: [u64; 4] = [0; 4];
    let bit_count = size * size - 1; // Exclude DC component
    
    // Compute mean of AC components
    let mean: f64 = dct_result[1..].iter().sum::<f64>() / bit_count as f64;

    // Generate hash bits based on comparison to mean
    for (i, &val) in dct_result.iter().enumerate().skip(1) {
        if val > mean {
            let bit_index = i - 1;
            let word_index = bit_index / 64;
            let bit_pos = bit_index % 64;
            if word_index < 4 {
                hash_bits[word_index] |= 1u64 << bit_pos;
            }
        }
    }

    Some(PerceptualHash { bits: hash_bits })
}

/// Compute 2D DCT using row-column FFT method
fn compute_2d_dct(data: &[f64], size: usize) -> Vec<f64> {
    let mut result = data.to_vec();
    
    // Row-wise DCT
    for row in 0..size {
        let start = row * size;
        let end = start + size;
        let row_data: Vec<Complex<f64>> = result[start..end]
            .iter()
            .map(|&x| Complex::new(x, 0.0))
            .collect();
        
        let row_dct = compute_1d_dct(&row_data);
        for (i, val) in row_dct.iter().take(size).enumerate() {
            result[start + i] = val.re;
        }
    }

    // Column-wise DCT
    for col in 0..size {
        let mut col_data: Vec<Complex<f64>> = Vec::with_capacity(size);
        for row in 0..size {
            col_data.push(Complex::new(result[row * size + col], 0.0));
        }
        
        let col_dct = compute_1d_dct(&col_data);
        for (row, val) in col_dct.iter().take(size).enumerate() {
            result[row * size + col] = val.re;
        }
    }

    result
}

/// Compute 1D DCT-II using FFT
fn compute_1d_dct(input: &[Complex<f64>]) -> Vec<Complex<f64>> {
    let n = input.len();
    if n == 0 {
        return vec![];
    }

    // Reorder input for DCT via FFT
    let mut reordered: Vec<Complex<f64>> = Vec::with_capacity(2 * n);
    for i in 0..n {
        reordered.push(input[i]);
    }
    for i in (0..n).rev() {
        reordered.push(input[i]);
    }

    // Compute FFT
    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(2 * n);
    fft.process(&mut reordered);

    // Extract DCT coefficients
    let mut result: Vec<Complex<f64>> = Vec::with_capacity(n);
    for k in 0..n {
        let twiddle = Complex::new(
            (-(k as f64) * std::f64::consts::PI / (2.0 * n as f64)).cos(),
            (-(k as f64) * std::f64::consts::PI / (2.0 * n as f64)).sin(),
        );
        result.push(reordered[k] * twiddle);
    }

    result
}

/// Compute brightness statistics for a frame
pub fn compute_brightness_stats(image: &DynamicImage) -> BrightnessStats {
    let gray = image.to_luma8();
    let mut sum: u64 = 0;
    let mut sum_sq: u64 = 0;
    let mut min_val: u8 = 255;
    let mut max_val: u8 = 0;
    let count = gray.pixels().count() as f32;

    for pixel in gray.pixels() {
        let val = pixel[0];
        sum += val as u64;
        sum_sq += (val as u64) * (val as u64);
        if val < min_val { min_val = val; }
        if val > max_val { max_val = val; }
    }

    let mean = sum as f32 / count;
    let variance = (sum_sq as f32 / count) - (mean * mean);
    let stddev = variance.sqrt();

    BrightnessStats {
        mean,
        stddev,
        min: min_val,
        max: max_val,
    }
}

/// Detect if frame is blank (single color or near-uniform)
pub fn is_blank_frame(image: &DynamicImage, config: &ProbeConfig) -> bool {
    let stats = compute_brightness_stats(image);
    stats.stddev < config.blank_frame_stddev_threshold
}

/// Compute motion statistics using frame difference (simplified optical flow)
pub fn compute_motion_stats(
    prev_frame: &DynamicImage,
    curr_frame: &DynamicImage,
    config: &ProbeConfig,
) -> Option<MotionStats> {
    if prev_frame.dimensions() != curr_frame.dimensions() {
        return None;
    }

    let prev_gray = prev_frame.to_luma8();
    let curr_gray = curr_frame.to_luma8();
    
    let mut magnitudes: Vec<f32> = Vec::new();
    let window_size = 3;

    for y in (window_size..prev_gray.height() as usize - window_size).step_by(2) {
        for x in (window_size..prev_gray.width() as usize - window_size).step_by(2) {
            // Simple block matching for motion estimation
            let prev_block = get_block_mean(&prev_gray, x, y, window_size);
            let curr_block = get_block_mean(&curr_gray, x, y, window_size);
            
            let diff = (curr_block - prev_block).abs();
            magnitudes.push(diff);
        }
    }

    if magnitudes.is_empty() {
        return None;
    }

    let mean = magnitudes.iter().sum::<f32>() / magnitudes.len() as f32;
    let max = magnitudes.iter().cloned().fold(0.0f32, f32::max);
    
    let variance = magnitudes.iter()
        .map(|&x| (x - mean).powi(2))
        .sum::<f32>() / magnitudes.len() as f32;
    let std = variance.sqrt();

    let high_motion_count = magnitudes.iter()
        .filter(|&&m| m > config.motion_detection_threshold)
        .count();

    Some(MotionStats {
        mean_magnitude: mean,
        max_magnitude: max,
        std_magnitude: std,
        high_motion_pixels: high_motion_count,
        motion_ratio: high_motion_count as f32 / magnitudes.len() as f32,
    })
}

fn get_block_mean(
    image: &image::GrayImage,
    x: usize,
    y: usize,
    half_size: usize,
) -> f32 {
    let mut sum = 0.0f32;
    let mut count = 0u32;

    for dy in 0..half_size * 2 {
        for dx in 0..half_size * 2 {
            let px = x + dx;
            let py = y + dy;
            if px < image.width() as usize && py < image.height() as usize {
                sum += image.get_pixel(px as u32, py as u32)[0] as f32;
                count += 1;
            }
        }
    }

    if count == 0 {
        0.0
    } else {
        sum / count as f32
    }
}

/// Compute Structural Similarity Index (SSIM)
pub fn compute_ssim(
    img1: &DynamicImage,
    img2: &DynamicImage,
) -> Option<SSIMResult> {
    if img1.dimensions() != img2.dimensions() {
        return None;
    }

    let gray1 = img1.to_luma8();
    let gray2 = img2.to_luma8();

    let width = gray1.width() as usize;
    let height = gray1.height() as usize;
    let total_pixels = width * height;

    // Constants for SSIM
    let l = 255.0f64;
    let k1 = 0.01;
    let k2 = 0.03;
    let c1 = (k1 * l).powi(2);
    let c2 = (k2 * l).powi(2);

    // Compute local statistics using sliding window
    let window_size = 11;
    let half_win = window_size / 2;
    
    let mut ssim_sum = 0.0f64;
    let mut valid_regions = 0usize;

    for y in half_win..height - half_win {
        for x in half_win..width - half_win {
            let (mu1, mu2, sigma1_sq, sigma2_sq, sigma12) = 
                compute_window_stats(&gray1, &gray2, x, y, half_win);

            let mu1 = mu1 as f64;
            let mu2 = mu2 as f64;
            let sigma1_sq = sigma1_sq as f64;
            let sigma2_sq = sigma2_sq as f64;
            let sigma12 = sigma12 as f64;

            let numerator = (2.0 * mu1 * mu2 + c1) * (2.0 * sigma12 + c2);
            let denominator = (mu1.powi(2) + mu2.powi(2) + c1) * 
                             (sigma1_sq + sigma2_sq + c2);

            if denominator > 0.0 {
                ssim_sum += numerator / denominator;
                valid_regions += 1;
            }
        }
    }

    if valid_regions == 0 {
        return None;
    }

    let mean_ssim = ssim_sum / valid_regions as f64;

    Some(SSIMResult {
        score: mean_ssim as f32,
        mean_score: mean_ssim as f32,
    })
}

fn compute_window_stats(
    img1: &image::GrayImage,
    img2: &image::GrayImage,
    cx: usize,
    cy: usize,
    half_win: usize,
) -> (f32, f32, f32, f32, f32) {
    let mut sum1 = 0.0f32;
    let mut sum2 = 0.0f32;
    let mut sum1_sq = 0.0f32;
    let mut sum2_sq = 0.0f32;
    let mut sum_prod = 0.0f32;
    let mut count = 0u32;

    for dy in 0..half_win * 2 + 1 {
        for dx in 0..half_win * 2 + 1 {
            let x = cx + dx - half_win;
            let y = cy + dy - half_win;

            if x < img1.width() as usize && y < img1.height() as usize {
                let p1 = img1.get_pixel(x as u32, y as u32)[0] as f32;
                let p2 = img2.get_pixel(x as u32, y as u32)[0] as f32;

                sum1 += p1;
                sum2 += p2;
                sum1_sq += p1 * p1;
                sum2_sq += p2 * p2;
                sum_prod += p1 * p2;
                count += 1;
            }
        }
    }

    let n = count as f32;
    let mu1 = sum1 / n;
    let mu2 = sum2 / n;
    let sigma1_sq = (sum1_sq / n) - (mu1 * mu1);
    let sigma2_sq = (sum2_sq / n) - (mu2 * mu2);
    let sigma12 = (sum_prod / n) - (mu1 * mu2);

    (mu1, mu2, sigma1_sq.max(0.0), sigma2_sq.max(0.0), sigma12)
}

/// Compute edge density using Sobel operator
pub fn compute_edge_density(image: &DynamicImage) -> f32 {
    let gray = image.to_luma8();
    let width = gray.width() as usize;
    let height = gray.height() as usize;

    // Sobel kernels
    let sobel_x = [-1, 0, 1, -2, 0, 2, -1, 0, 1];
    let sobel_y = [-1, -2, -1, 0, 0, 0, 1, 2, 1];

    let mut edge_sum = 0.0f32;
    let mut total_pixels = 0usize;

    for y in 1..height - 1 {
        for x in 1..width - 1 {
            let mut gx = 0.0f32;
            let mut gy = 0.0f32;

            for ky in 0..3 {
                for kx in 0..3 {
                    let px = gray.get_pixel((x + kx - 1) as u32, (y + ky - 1) as u32)[0] as f32;
                    let idx = ky * 3 + kx;
                    gx += px * sobel_x[idx] as f32;
                    gy += px * sobel_y[idx] as f32;
                }
            }

            let magnitude = (gx * gx + gy * gy).sqrt();
            edge_sum += magnitude;
            total_pixels += 1;
        }
    }

    if total_pixels == 0 {
        0.0
    } else {
        edge_sum / total_pixels as f32
    }
}

/// Compute visual complexity score (combination of edge density and variance)
pub fn compute_complexity_score(image: &DynamicImage) -> f32 {
    let edge_density = compute_edge_density(image);
    let brightness = compute_brightness_stats(image);
    
    // Normalize edge density (typical range 0-50)
    let normalized_edges = (edge_density / 50.0).min(1.0);
    
    // Normalize stddev (typical range 0-100)
    let normalized_variance = (brightness.stddev / 100.0).min(1.0);
    
    // Weighted combination
    0.6 * normalized_edges + 0.4 * normalized_variance
}

/// Full frame analysis combining all metrics
pub fn analyze_frame(
    image: &DynamicImage,
    prev_frame: Option<&DynamicImage>,
    config: &ProbeConfig,
) -> FrameAnalysis {
    let perceptual_hash = compute_perceptual_hash(image, config);
    let brightness = compute_brightness_stats(image);
    let is_blank = is_blank_frame(image, config);
    let edge_density = compute_edge_density(image);
    let complexity = compute_complexity_score(image);

    let motion = prev_frame.and_then(|prev| {
        compute_motion_stats(prev, image, config)
    });

    FrameAnalysis {
        perceptual_hash,
        brightness: Some(brightness),
        motion,
        is_blank,
        edge_density,
        complexity_score: complexity,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::{Rgb, RgbImage};

    #[test]
    fn test_perceptual_hash_similarity() {
        // Create two similar images
        let mut img1 = RgbImage::new(16, 16);
        let mut img2 = RgbImage::new(16, 16);

        for x in 0..16 {
            for y in 0..16 {
                img1.put_pixel(x, y, Rgb([x as u8 * 16, y as u8 * 16, 128]));
                img2.put_pixel(x, y, Rgb([x as u8 * 16 + 1, y as u8 * 16, 128]));
            }
        }

        let config = ProbeConfig::default();
        let hash1 = compute_perceptual_hash(&DynamicImage::ImageRgb8(img1), &config).unwrap();
        let hash2 = compute_perceptual_hash(&DynamicImage::ImageRgb8(img2), &config).unwrap();

        // Similar images should have low hamming distance
        assert!(hash1.is_similar(&hash2, config.hamming_threshold));
    }

    #[test]
    fn test_blank_frame_detection() {
        let config = ProbeConfig::default();
        
        // Uniform image should be detected as blank
        let uniform = DynamicImage::new_luma8(64, 64);
        assert!(is_blank_frame(&uniform, &config));

        // Complex image should not be blank
        let mut complex = RgbImage::new(64, 64);
        for x in 0..64 {
            for y in 0..64 {
                complex.put_pixel(x, y, Rgb([x as u8, y as u8, (x + y) as u8]));
            }
        }
        assert!(!is_blank_frame(&DynamicImage::ImageRgb8(complex), &config));
    }

    #[test]
    fn test_brightness_stats() {
        let mut img = RgbImage::new(10, 10);
        for x in 0..10 {
            for y in 0..10 {
                img.put_pixel(x, y, Rgb([128, 128, 128]));
            }
        }

        let stats = compute_brightness_stats(&DynamicImage::ImageRgb8(img));
        assert!((stats.mean - 128.0).abs() < 1.0);
        assert_eq!(stats.stddev, 0.0);
    }
}
