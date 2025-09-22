import React from 'react';
import { useParams } from 'react-router-dom';
import { mockArticles } from '../data/mockData';

const ArticlePage: React.FC = () => {
  const { articleSlug } = useParams();
  const article = mockArticles.find(a => a.slug === articleSlug);

  if (!article) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center py-12">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Article Not Found</h1>
          <p className="text-gray-600">The article you're looking for doesn't exist.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <article>
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">{article.title}</h1>
          <div className="flex items-center space-x-4 mb-6">
            <img
              src={article.author.avatar}
              alt={article.author.name}
              className="w-12 h-12 rounded-full"
              onError={(e) => {
                e.currentTarget.src = '/placeholder-avatar.png';
              }}
            />
            <div>
              <div className="font-medium text-gray-900">{article.author.name}</div>
              <div className="text-gray-500 text-sm">
                {new Date(article.publishedAt).toLocaleDateString()} • {article.readTime} min read
              </div>
            </div>
          </div>
        </header>

        <div className="prose prose-lg max-w-none">
          <div dangerouslySetInnerHTML={{ __html: article.content.replace(/\n/g, '<br>') }} />
        </div>
      </article>
    </div>
  );
};

export default ArticlePage;