import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeftIcon, ChevronRightIcon, ArrowRightIcon } from '@heroicons/react/24/outline';

import { mockPredictions } from '../../data/mockPredictions';
import Container, { Section } from '../layout/Container';
import PredictionCard from '../ui/PredictionCard';
import Button from '../ui/Button';

const FeaturedPredictions: React.FC = () => {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isAutoPlaying, setIsAutoPlaying] = useState(true);

  // Get featured predictions (high confidence ones)
  const featuredPredictions = mockPredictions
    .filter(p => p.confidence >= 75)
    .slice(0, 6);

  const itemsPerSlide = 3;
  const totalSlides = Math.ceil(featuredPredictions.length / itemsPerSlide);

  // Auto-play functionality
  useEffect(() => {
    if (!isAutoPlaying) return;

    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % totalSlides);
    }, 5000);

    return () => clearInterval(interval);
  }, [isAutoPlaying, totalSlides]);

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % totalSlides);
    setIsAutoPlaying(false);
  };

  const prevSlide = () => {
    setCurrentSlide((prev) => (prev - 1 + totalSlides) % totalSlides);
    setIsAutoPlaying(false);
  };

  const goToSlide = (index: number) => {
    setCurrentSlide(index);
    setIsAutoPlaying(false);
  };



  return (
    <Section padding="lg" background="dark">
      <Container>
        {/* Section Header */}
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Featured <span className="gradient-text">Predictions</span>
          </h2>
          <p className="text-lg text-dark-300 max-w-2xl mx-auto">
            Our highest confidence predictions for today's matches. 
            Based on advanced analytics and expert analysis.
          </p>
        </div>

        {/* Carousel Container */}
        <div className="relative">
          {/* Navigation Buttons */}
          <button
            onClick={prevSlide}
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-4 z-10 w-12 h-12 bg-dark-800 hover:bg-dark-700 border border-dark-600 rounded-full flex items-center justify-center text-white transition-all duration-200 hover:scale-110"
            disabled={totalSlides <= 1}
          >
            <ChevronLeftIcon className="w-6 h-6" />
          </button>

          <button
            onClick={nextSlide}
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-4 z-10 w-12 h-12 bg-dark-800 hover:bg-dark-700 border border-dark-600 rounded-full flex items-center justify-center text-white transition-all duration-200 hover:scale-110"
            disabled={totalSlides <= 1}
          >
            <ChevronRightIcon className="w-6 h-6" />
          </button>

          {/* Predictions Grid */}
          <div className="overflow-hidden">
            <div
              className="flex transition-transform duration-500 ease-in-out"
              style={{
                transform: `translateX(-${currentSlide * 100}%)`,
              }}
            >
              {Array.from({ length: totalSlides }).map((_, slideIndex) => (
                <div
                  key={slideIndex}
                  className="w-full flex-shrink-0"
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {featuredPredictions
                      .slice(slideIndex * itemsPerSlide, (slideIndex + 1) * itemsPerSlide)
                      .map((prediction) => (
                        <div
                          key={prediction.id}
                          className="transform hover:scale-105 transition-transform duration-300"
                        >
                          <PredictionCard
                            prediction={prediction}
                            onViewDetails={() => {
                              // Navigate to prediction details
                            }}
                          />
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Slide Indicators */}
          {totalSlides > 1 && (
            <div className="flex justify-center mt-8 space-x-2">
              {Array.from({ length: totalSlides }).map((_, index) => (
                <button
                  key={index}
                  onClick={() => goToSlide(index)}
                  className={`w-3 h-3 rounded-full transition-all duration-200 ${
                    index === currentSlide
                      ? 'bg-primary-600 scale-125'
                      : 'bg-dark-600 hover:bg-dark-500'
                  }`}
                />
              ))}
            </div>
          )}
        </div>

        {/* View All Button */}
        <div className="text-center mt-12">
          <Link to="/predictions">
            <Button
              variant="outline"
              size="lg"
              icon={<ArrowRightIcon className="w-5 h-5" />}
              iconPosition="right"
            >
              View All Predictions
            </Button>
          </Link>
        </div>

        {/* Auto-play Control */}
        <div className="flex justify-center mt-6">
          <button
            onClick={() => setIsAutoPlaying(!isAutoPlaying)}
            className="text-sm text-dark-400 hover:text-white transition-colors duration-200"
          >
            {isAutoPlaying ? 'Pause Auto-play' : 'Resume Auto-play'}
          </button>
        </div>
      </Container>
    </Section>
  );
};

export default FeaturedPredictions;
