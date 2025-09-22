import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { mockArticles } from '../data/mockData';
import { ArticleCategory } from '../types';

const BettingAcademyPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  const filteredArticles = selectedCategory === 'all'
    ? mockArticles
    : mockArticles.filter(article => article.category === selectedCategory);

  const categories = [
    { key: 'all', label: 'All Categories', count: mockArticles.length },
    ...Object.values(ArticleCategory).map(category => ({
      key: category,
      label: category,
      count: mockArticles.filter(article => article.category === category).length
    }))
  ];

  const featuredArticle = mockArticles.find(article => article.isFeature);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">Betting Academy</h1>
        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
          Master the art of sports betting with our comprehensive guides, strategies, and expert insights.
          Learn from professionals and improve your betting skills.
        </p>
      </div>

      {/* Featured Article */}
      {featuredArticle && (
        <div className="mb-12">
          <div className="bg-gradient-to-r from-purple-600 to-purple-700 rounded-2xl overflow-hidden">
            <div className="p-8 lg:p-12 text-white">
              <div className="grid lg:grid-cols-2 gap-8 items-center">
                <div>
                  <span className="inline-block px-3 py-1 bg-purple-500 bg-opacity-50 rounded-full text-sm font-medium mb-4">
                    Featured Article
                  </span>
                  <h2 className="text-3xl lg:text-4xl font-bold mb-4 leading-tight">
                    {featuredArticle.title}
                  </h2>
                  <p className="text-purple-100 text-lg mb-6">
                    {featuredArticle.excerpt}
                  </p>
                  <div className="flex items-center space-x-4 mb-6">
                    <img
                      src={featuredArticle.author.avatar}
                      alt={featuredArticle.author.name}
                      className="w-10 h-10 rounded-full"
                      onError={(e) => {
                        e.currentTarget.src = '/placeholder-avatar.png';
                      }}
                    />
                    <div>
                      <div className="font-medium">{featuredArticle.author.name}</div>
                      <div className="text-purple-200 text-sm">
                        {formatDate(featuredArticle.publishedAt)} • {featuredArticle.readTime} min read
                      </div>
                    </div>
                  </div>
                  <Link
                    to={`/academy/${featuredArticle.slug}`}
                    className="btn bg-white text-purple-600 hover:bg-gray-100 font-semibold px-6 py-3"
                  >
                    Read Article
                  </Link>
                </div>
                <div className="hidden lg:block">
                  <img
                    src={featuredArticle.featuredImage}
                    alt={featuredArticle.title}
                    className="rounded-xl shadow-2xl"
                    onError={(e) => {
                      e.currentTarget.src = '/placeholder-article.jpg';
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Categories Filter */}
      <div className="mb-8">
        <div className="flex flex-wrap gap-3">
          {categories.map((category) => (
            <button
              key={category.key}
              onClick={() => setSelectedCategory(category.key)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors duration-200 ${
                selectedCategory === category.key
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {category.label} ({category.count})
            </button>
          ))}
        </div>
      </div>

      {/* Articles Grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
        {filteredArticles.map((article) => (
          <article key={article.id} className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-lg transition-shadow duration-200">
            <img
              src={article.featuredImage}
              alt={article.title}
              className="w-full h-48 object-cover"
              onError={(e) => {
                e.currentTarget.src = '/placeholder-article.jpg';
              }}
            />
            <div className="p-6">
              <div className="flex items-center space-x-2 mb-3">
                <span className="px-2 py-1 bg-purple-100 text-purple-700 text-xs font-medium rounded">
                  {article.category}
                </span>
                <span className="text-gray-500 text-sm">
                  {article.readTime} min read
                </span>
              </div>

              <h3 className="text-xl font-bold text-gray-900 mb-3 line-clamp-2">
                {article.title}
              </h3>

              <p className="text-gray-600 mb-4 line-clamp-3">
                {article.excerpt}
              </p>

              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <img
                    src={article.author.avatar}
                    alt={article.author.name}
                    className="w-8 h-8 rounded-full"
                    onError={(e) => {
                      e.currentTarget.src = '/placeholder-avatar.png';
                    }}
                  />
                  <div>
                    <div className="font-medium text-sm text-gray-900">
                      {article.author.name}
                    </div>
                    <div className="text-gray-500 text-xs">
                      {formatDate(article.publishedAt)}
                    </div>
                  </div>
                </div>

                <Link
                  to={`/academy/${article.slug}`}
                  className="text-purple-600 hover:text-purple-700 font-medium text-sm flex items-center"
                >
                  Read More
                  <svg className="ml-1 w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </Link>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* Learning Path Section */}
      <div className="mt-16">
        <h2 className="text-3xl font-bold text-gray-900 mb-8 text-center">
          Structured Learning Path
        </h2>

        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-purple-600">1</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Basics
            </h3>
            <p className="text-gray-600 text-sm">
              Learn fundamental concepts, odds, and basic betting principles
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-purple-600">2</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Strategy
            </h3>
            <p className="text-gray-600 text-sm">
              Develop advanced strategies and understand market analysis
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-purple-600">3</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Management
            </h3>
            <p className="text-gray-600 text-sm">
              Master bankroll management and risk assessment techniques
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl font-bold text-purple-600">4</span>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Psychology
            </h3>
            <p className="text-gray-600 text-sm">
              Understand betting psychology and emotional control
            </p>
          </div>
        </div>
      </div>

      {/* Newsletter Signup */}
      <div className="mt-16 bg-gray-50 rounded-2xl p-8 text-center">
        <h3 className="text-2xl font-bold text-gray-900 mb-4">
          Stay Updated with New Content
        </h3>
        <p className="text-gray-600 mb-6 max-w-2xl mx-auto">
          Get the latest betting guides, strategies, and expert insights delivered directly to your inbox.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 max-w-md mx-auto">
          <input
            type="email"
            placeholder="Enter your email"
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          />
          <button className="btn btn-primary px-6 py-3 whitespace-nowrap">
            Subscribe
          </button>
        </div>
      </div>
    </div>
  );
};

export default BettingAcademyPage;